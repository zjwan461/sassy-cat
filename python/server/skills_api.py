# -*- coding: utf-8 -*-
"""
技能（Skills）REST API：

- GET    /api/skills                列出 runtime/skills 下全部技能（名称/描述/文件数等）
- POST   /api/skills                新建技能目录（body: {name}，自动生成 SKILL.md 骨架）
- POST   /api/skills/import         导入技能 zip 包（multipart: file，可选 name/overwrite）
- DELETE /api/skills/{name}         删除整个技能目录（不可恢复）
- GET    /api/skills/{name}/export  导出技能为 zip 压缩包下载
- GET    /api/skills/{name}         技能详情（SKILL.md frontmatter + 完整目录树）
- GET    /api/skills/{name}/file?path=rel  读取技能内任意文本文件
- PUT    /api/skills/{name}/file    修改技能内任意文本文件（body: {path, content}）

安全约束：所有相对 path 都做规范化 + 越界校验（realpath 必须落在技能目录内），
技能名本身也不允许包含路径分隔符或 ".."。
"""

import io
import logging
import os
import re
import shutil
import tempfile
import zipfile
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from agent.constant import WORK_DIR

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/skills", tags=["skills"])

# 技能根目录：runtime/skills（与 agent 加载的 /skills 虚拟目录一致）
SKILLS_ROOT = os.path.realpath(os.path.join(WORK_DIR, "skills"))
# 单文件读取上限 2MB，避免误读大二进制把响应撑爆
MAX_READ_SIZE = 2 * 1024 * 1024
# 导入 zip 包上限 20MB
MAX_IMPORT_SIZE = 20 * 1024 * 1024
# 导出/导入时忽略的噪音文件与目录
_IGNORED_IMPORT_PARTS = {"__MACOSX", ".git", "__pycache__", "node_modules"}


def _looks_textual(path: str) -> bool:
    """启发式文本判定：不含 NUL 字节且可 UTF-8 解码即视为可在线编辑的文本。

    这样任意脚本/配置文件（.py/.mjs/.lua/.tpl/无扩展名等）都能编辑，
    不再受扩展名白名单限制；真二进制文件仍会被拒绝。
    """
    try:
        with open(path, "rb") as f:
            head = f.read(8192)
        if b"\x00" in head:
            return False
        try:
            head.decode("utf-8")
        except UnicodeDecodeError:
            # 前缀截断可能切开多字节字符，回退 GBK 也试一下常见中文编码
            try:
                head.decode("gbk")
            except UnicodeDecodeError:
                return False
        return True
    except OSError:
        return False


class SkillFilePayload(BaseModel):
    path: str
    content: str


class SkillCreatePayload(BaseModel):
    name: str


# 技能目录名：字母/数字/下划线开头，允许 - _ .，禁止路径分隔符与 ".."
_SKILL_NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]{0,63}$")


def _validated_skill_dir(name: str, *, must_exist: bool = True) -> str:
    """技能名 -> 绝对目录，校验合法性；must_exist 时要求目录已存在。"""
    if (
        not name
        or name in (".", "..")
        or ".." in name
        or "/" in name
        or "\\" in name
        or not _SKILL_NAME_RE.match(name)
    ):
        raise HTTPException(status_code=400, detail="非法的技能名称（仅限字母、数字、-、_、.）")
    skill_dir = os.path.realpath(os.path.join(SKILLS_ROOT, name))
    if not skill_dir.startswith(SKILLS_ROOT + os.sep) and skill_dir != SKILLS_ROOT:
        raise HTTPException(status_code=400, detail="非法的技能名称")
    if must_exist and not os.path.isdir(skill_dir):
        raise HTTPException(status_code=404, detail="技能不存在")
    return skill_dir


def _safe_skill_dir(name: str) -> str:
    """技能名 -> 绝对目录，校验不越界且真实存在。"""
    return _validated_skill_dir(name)


def _safe_file_path(skill_dir: str, rel_path: str) -> str:
    """技能内相对路径 -> 绝对路径，校验规范化后仍落在技能目录内。"""
    if not rel_path:
        raise HTTPException(status_code=400, detail="缺少文件路径")
    # 统一分隔符并拒绝绝对路径盘符
    rel = rel_path.replace("\\", "/").lstrip("/")
    if ":" in rel.split("/")[0]:
        raise HTTPException(status_code=400, detail="非法的文件路径")
    target = os.path.realpath(os.path.join(skill_dir, *rel.split("/")))
    if not target.startswith(skill_dir + os.sep):
        raise HTTPException(status_code=400, detail="非法的文件路径（越界）")
    return target


def _is_text_file(path: str) -> bool:
    # 备份文件（.bak）只读展示，不在线编辑，避免管理界面噪音
    if path.endswith(".bak"):
        return False
    return _looks_textual(path)


def _parse_frontmatter(content: str) -> dict:
    """极简 YAML frontmatter 解析（key: value 与 key: > 多行折叠），够 SKILL.md 用。"""
    if not content.startswith("---"):
        return {}
    lines = content.splitlines()
    meta, key, buf = {}, None, []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        # 顶层 key: value
        if line and not line[0].isspace():
            if buf and key:
                meta[key] = " ".join(buf).strip()
            buf = []
            if ":" in line:
                k, v = line.split(":", 1)
                key, meta_k = k.strip(), v.strip()
                if meta_k and meta_k not in (">", "|", ">-", "|-"):
                    meta[key] = meta_k
                    key = None
        elif line.strip() and key:  # 缩进续行（多行描述）
            buf.append(line.strip())
    if buf and key:
        meta[key] = " ".join(buf).strip()
    return meta


def _scan_tree(dir_path: str, rel: str = "") -> list:
    """递归扫描目录，返回排序后的文件树节点列表。"""
    entries = []
    try:
        items = sorted(os.listdir(dir_path), key=lambda s: (os.path.isdir(os.path.join(dir_path, s)) is False, s.lower()))
    except OSError:
        return entries
    for item in items:
        if item.startswith("."):
            continue
        abs_path = os.path.join(dir_path, item)
        child_rel = f"{rel}/{item}" if rel else item
        if os.path.isdir(abs_path):
            children = _scan_tree(abs_path, child_rel)
            entries.append({"name": item, "path": child_rel, "type": "dir", "children": children})
        else:
            try:
                size = os.path.getsize(abs_path)
            except OSError:
                size = 0
            entries.append({
                "name": item,
                "path": child_rel,
                "type": "file",
                "size": size,
                "text": _is_text_file(abs_path),
            })
    return entries


def _count_files(tree: list) -> tuple:
    """统计 (文件总数, references 文件数, scripts 文件数)。"""
    total = refs = scripts = 0
    for node in tree:
        if node["type"] == "file":
            total += 1
        else:
            sub_total, sub_refs, sub_scripts = _count_files(node["children"])
            total += sub_total
            refs += sub_refs
            scripts += sub_scripts
    return total, refs, scripts


def _section_counts(tree: list, top_dir: str) -> int:
    """技能根下某个目录（references/scripts）内文件数。"""
    for node in tree:
        if node["type"] == "dir" and node["name"].lower() == top_dir:
            total, _, _ = _count_files(node["children"])
            return total
    return 0


@router.get("")
async def list_skills():
    """列出 runtime/skills 下全部技能卡片信息。"""
    if not os.path.isdir(SKILLS_ROOT):
        return {"items": []}
    items = []
    for name in sorted(os.listdir(SKILLS_ROOT), key=str.lower):
        skill_dir = os.path.realpath(os.path.join(SKILLS_ROOT, name))
        if not name.startswith(".") and os.path.isdir(skill_dir):
            tree = _scan_tree(skill_dir)
            skill_md = os.path.join(skill_dir, "SKILL.md")
            meta = {}
            if os.path.isfile(skill_md):
                try:
                    with open(skill_md, "r", encoding="utf-8") as f:
                        meta = _parse_frontmatter(f.read(8192))
                except (OSError, UnicodeDecodeError):
                    meta = {}
            try:
                mtime = os.path.getmtime(skill_dir)
            except OSError:
                mtime = 0
            total, _, _ = _count_files(tree)
            items.append({
                "name": name,
                "displayName": meta.get("name") or name,
                "description": meta.get("description") or "",
                "fileCount": total,
                "referenceCount": _section_counts(tree, "references"),
                "scriptCount": _section_counts(tree, "scripts"),
                "hasSkillMd": os.path.isfile(skill_md),
                "updatedAt": int(mtime * 1000),
            })
    return {"items": items}


def _skill_md_skeleton(name: str) -> str:
    """新建技能时生成的 SKILL.md 骨架（含 frontmatter，便于 agent 识别）。"""
    return (
        "---\n"
        f"name: {name}\n"
        "description: >\n"
        "  TODO：填写技能描述，说明该技能的用途与触发时机。\n"
        "---\n\n"
        f"# {name}\n\n"
        "## 使用说明\n\n"
        "TODO：补充技能的详细使用步骤、脚本调用方式与注意事项。\n"
    )


@router.post("")
async def create_skill(payload: SkillCreatePayload):
    """新建技能：在 runtime/skills 下创建同名目录并生成 SKILL.md 骨架。"""
    name = payload.name.strip()
    skill_dir = _validated_skill_dir(name, must_exist=False)
    if os.path.exists(skill_dir):
        raise HTTPException(status_code=409, detail="同名技能已存在")
    try:
        os.makedirs(SKILLS_ROOT, exist_ok=True)
        os.mkdir(skill_dir)
        with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write(_skill_md_skeleton(name))
    except OSError as e:
        logger.exception(f"创建技能失败: {skill_dir}")
        # 回滚半成品目录，避免留下无 SKILL.md 的脏目录
        if os.path.isdir(skill_dir):
            shutil.rmtree(skill_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=str(e))
    logger.info(f"技能已创建: {name}")
    return {"status": "success", "name": name}


@router.delete("/{name}")
async def delete_skill(name: str):
    """删除整个技能目录（递归删除，不可恢复）。"""
    skill_dir = _safe_skill_dir(name)
    try:
        shutil.rmtree(skill_dir)
    except OSError as e:
        logger.exception(f"删除技能失败: {skill_dir}")
        raise HTTPException(status_code=500, detail=str(e))
    logger.info(f"技能已删除: {name}")
    return {"status": "success", "name": name}


def _is_ignored_entry(rel_parts: list) -> bool:
    """zip 条目路径中任一段命中噪音目录或 . 前缀文件即忽略。"""
    for part in rel_parts:
        if part in _IGNORED_IMPORT_PARTS or (part.startswith(".") and part not in (".", "..")):
            return True
    return False


@router.get("/{name}/export")
async def export_skill(name: str):
    """把技能目录打包为 zip 返回下载（zip 内含以技能名命名的顶层目录）。"""
    skill_dir = _safe_skill_dir(name)
    buf = io.BytesIO()
    try:
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(skill_dir):
                # 就地过滤噪音目录，避免无谓遍历
                dirs[:] = [d for d in dirs if d not in _IGNORED_IMPORT_PARTS and not d.startswith(".")]
                for fn in files:
                    if fn.endswith(".bak") or fn.startswith("."):
                        continue
                    abs_path = os.path.join(root, fn)
                    rel = os.path.relpath(abs_path, skill_dir).replace("\\", "/")
                    zf.write(abs_path, f"{name}/{rel}")
    except OSError as e:
        logger.exception(f"导出技能失败: {skill_dir}")
        raise HTTPException(status_code=500, detail=str(e))
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}.zip"'},
    )


@router.post("/import")
async def import_skill(
    file: UploadFile = File(..., description="技能 zip 包"),
    name: Optional[str] = Form(None, description="目标技能名，缺省取 zip 顶层目录名"),
    overwrite: bool = Form(False, description="同名技能已存在时是否覆盖"),
):
    """导入技能：上传 zip 包解压到 runtime/skills/{name}。

    zip 结构兼容两种：顶层单目录（my-skill/SKILL.md）或直接根含 SKILL.md。
    """
    raw = await file.read()
    if len(raw) > MAX_IMPORT_SIZE:
        raise HTTPException(status_code=413, detail="zip 包超过 20MB 导入限制")
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="文件不是合法的 zip 包")
    with zf:
        # 收集有效条目并确定技能名
        entries = []
        top_dirs = set()
        for info in zf.infolist():
            if info.is_dir():
                continue
            parts = [p for p in info.filename.replace("\\", "/").split("/") if p not in ("", ".")]
            if not parts or _is_ignored_entry(parts):
                continue
            if ".." in parts:
                raise HTTPException(status_code=400, detail=f"zip 内含越界路径：{info.filename}")
            if len(parts) == 1:
                # 根级只接受 SKILL.md（无顶层目录的裸包），其余散落文件忽略
                if parts[0].lower() == "skill.md":
                    entries.append((parts, info))
                continue
            top_dirs.add(parts[0])
            entries.append((parts, info))

        if not entries:
            raise HTTPException(status_code=400, detail="zip 包内没有可导入的技能文件")
        # 推断技能名：显式 name > 唯一顶层目录 > 上传文件名
        derived = (name or "").strip()
        if not derived:
            if len(top_dirs) == 1:
                derived = top_dirs.pop()
            else:
                base = os.path.basename(file.filename or "").lower()
                if base.endswith(".zip"):
                    derived = base[:-4]
        if not derived:
            raise HTTPException(status_code=400, detail="无法确定技能名称，请手动指定")
        skill_dir = _validated_skill_dir(derived, must_exist=False)
        if os.path.exists(skill_dir):
            if not overwrite:
                raise HTTPException(status_code=409, detail=f"技能「{derived}」已存在，如需替换请勾选覆盖导入")
        # 逐条写盘（先全部校验再落盘，失败即清理临时目录）
        tmp_dir = skill_dir + ".importing"
        shutil.rmtree(tmp_dir, ignore_errors=True)
        try:
            total_written = 0
            for parts, info in entries:
                # 顶层目录与技能名一致时去掉该层；根级 SKILL.md 直接落到技能根
                if len(parts) > 1 and parts[0] == derived:
                    rel_parts = parts[1:]
                elif len(parts) == 1:
                    rel_parts = parts
                else:
                    rel_parts = parts  # 顶层目录名与技能名不同：保留原结构顶层
                target = os.path.realpath(os.path.join(tmp_dir, *rel_parts))
                if not target.startswith(os.path.realpath(tmp_dir) + os.sep):
                    raise HTTPException(status_code=400, detail=f"zip 内含越界路径：{info.filename}")
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with zf.open(info) as src, open(target, "wb") as dst:
                    dst.write(src.read())
                total_written += 1
            if total_written == 0:
                raise HTTPException(status_code=400, detail="zip 包内没有可导入的文件")
            if os.path.exists(skill_dir):
                shutil.rmtree(skill_dir)
            os.rename(tmp_dir, skill_dir)
        except HTTPException:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise
        except OSError as e:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            logger.exception(f"导入技能失败: {skill_dir}")
            raise HTTPException(status_code=500, detail=str(e))
    logger.info(f"技能已导入: {derived}（{len(entries)} 个文件）")
    return {"status": "success", "name": derived, "fileCount": len(entries)}


@router.get("/{name}")
async def get_skill(name: str):
    """技能详情：元信息 + 完整目录树。"""
    skill_dir = _safe_skill_dir(name)
    tree = _scan_tree(skill_dir)
    skill_md_path = os.path.join(skill_dir, "SKILL.md")
    skill_md = ""
    meta = {}
    if os.path.isfile(skill_md_path):
        try:
            with open(skill_md_path, "r", encoding="utf-8") as f:
                skill_md = f.read(MAX_READ_SIZE)
            meta = _parse_frontmatter(skill_md)
        except (OSError, UnicodeDecodeError):
            pass
    total, _, _ = _count_files(tree)
    return {
        "skill": {
            "name": name,
            "displayName": meta.get("name") or name,
            "description": meta.get("description") or "",
            "fileCount": total,
            "referenceCount": _section_counts(tree, "references"),
            "scriptCount": _section_counts(tree, "scripts"),
        },
        "tree": tree,
        "skillMd": skill_md,
    }


@router.get("/{name}/file")
async def read_skill_file(name: str, path: str = Query(..., description="技能内相对路径")):
    """读取技能内某个文本文件内容。"""
    skill_dir = _safe_skill_dir(name)
    target = _safe_file_path(skill_dir, path)
    if not os.path.isfile(target):
        raise HTTPException(status_code=404, detail="文件不存在")
    if os.path.getsize(target) > MAX_READ_SIZE:
        raise HTTPException(status_code=413, detail="文件过大，超过 2MB 读取限制")
    if not _is_text_file(target):
        raise HTTPException(status_code=400, detail="该文件类型不支持在线查看/编辑")
    try:
        with open(target, "r", encoding="utf-8") as f:
            content = f.read()
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="文件非 UTF-8 文本，不支持在线编辑")
    except OSError as e:
        logger.exception(f"读取技能文件失败: {target}")
        raise HTTPException(status_code=500, detail=str(e))
    return {"path": path.replace("\\", "/"), "content": content}


@router.delete("/{name}/file")
async def delete_skill_file(name: str, path: str = Query(..., description="技能内相对路径")):
    """删除技能内某个文件（连同其 .bak 备份一并清理）。"""
    skill_dir = _safe_skill_dir(name)
    target = _safe_file_path(skill_dir, path)
    if not os.path.isfile(target):
        raise HTTPException(status_code=404, detail="文件不存在")
    try:
        os.remove(target)
        backup = target + ".bak"
        if os.path.isfile(backup):
            os.remove(backup)
    except OSError as e:
        logger.exception(f"删除技能文件失败: {target}")
        raise HTTPException(status_code=500, detail=str(e))
    logger.info(f"技能文件已删除: {path}")
    return {"status": "success", "path": path.replace("\\", "/")}


@router.post("/{name}/file")
async def create_skill_file(name: str, payload: SkillFilePayload):
    """在技能内新增文本文件（可带相对子目录，自动创建；同名已存在则拒绝）。"""
    skill_dir = _safe_skill_dir(name)
    target = _safe_file_path(skill_dir, payload.path)
    if os.path.exists(target):
        raise HTTPException(status_code=409, detail="文件已存在，请直接编辑")
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(payload.content)
    except OSError as e:
        logger.exception(f"新增技能文件失败: {target}")
        raise HTTPException(status_code=500, detail=str(e))
    logger.info(f"技能文件已新增: {payload.path}")
    return {"status": "success", "path": payload.path.replace("\\", "/")}


@router.put("/{name}/file")
async def write_skill_file(name: str, payload: SkillFilePayload):
    """修改技能内某个文本文件（整文件覆写，写前备份 .bak）。"""
    skill_dir = _safe_skill_dir(name)
    target = _safe_file_path(skill_dir, payload.path)
    if not os.path.isfile(target):
        raise HTTPException(status_code=404, detail="文件不存在")
    if not _is_text_file(target):
        raise HTTPException(status_code=400, detail="该文件类型不支持在线编辑")
    try:
        # 先备份原文件，误改可找回
        backup = target + ".bak"
        with open(target, "r", encoding="utf-8") as f:
            original = f.read()
        with open(backup, "w", encoding="utf-8") as f:
            f.write(original)
        with open(target, "w", encoding="utf-8") as f:
            f.write(payload.content)
    except OSError as e:
        logger.exception(f"写入技能文件失败: {target}")
        raise HTTPException(status_code=500, detail=str(e))
    logger.info(f"技能文件已更新: {payload.path}（备份 {os.path.basename(backup)}）")
    return {"status": "success", "path": payload.path.replace("\\", "/")}
