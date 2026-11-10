# -*- coding: utf-8 -*-
"""数据备份：导出配置、对话、向量库、上传文件与技能。

设计取舍：
- 不做压缩包（避免引入额外依赖 / 跨平台打包差异），直接生成一个带时间戳的目录；
- SQLite 用官方 backup API 生成一致性快照，避免直接拷贝 WAL 中的半写状态；
- 不包含 checkpoints.sqlite（LangGraph 现场，常见 1GB+）；迁移后对话历史仍在，
  但旧会话的 Agent 现场需要重新开始，这是体积与完整性的折中。
"""

from __future__ import annotations

import logging
import os
import shutil
import sqlite3
import time
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import paths
from agent.constant import SKILLS_DIR

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/backup", tags=["backup"])


class ExportPayload(BaseModel):
    targetDir: str


def _copy_sqlite(src: str, dst: str) -> bool:
    """用 sqlite backup API 生成一致性快照。"""
    if not os.path.isfile(src):
        return False
    source = sqlite3.connect(src, timeout=10)
    try:
        target = sqlite3.connect(dst)
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()
    return True


def _dir_size(path: str) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


def _export_blocking(target_dir: str) -> dict[str, Any]:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = os.path.join(target_dir, f"sassy-cat-backup-{stamp}")
    suffix = 1
    while os.path.exists(dest):
        suffix += 1
        dest = os.path.join(target_dir, f"sassy-cat-backup-{stamp}-{suffix}")
    os.makedirs(dest, exist_ok=True)

    data_dir = paths.data_dir()
    items: list[dict[str, Any]] = []

    # 1) 配置 / 业务数据库（一致性快照）
    for name, out_name in (
        ("config.user.json", "config.user.json"),
        ("mcp-servers.json", "mcp-servers.json"),
        ("messages.sqlite", "messages.sqlite"),
    ):
        src = os.path.join(data_dir, name)
        dst = os.path.join(dest, out_name)
        if name.endswith(".sqlite"):
            ok = _copy_sqlite(src, dst)
        elif os.path.isfile(src):
            shutil.copy2(src, dst)
            ok = True
        else:
            ok = False
        if ok:
            items.append({"name": out_name, "size": os.path.getsize(dst)})

    # 2) 向量库与上传文件
    for name in ("chroma", "upload"):
        src = os.path.join(data_dir, name)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(dest, name), dirs_exist_ok=True)
            items.append({"name": name, "size": _dir_size(os.path.join(dest, name))})

    # 3) 技能库（应用 runtime/skills，不属于 userData）
    if os.path.isdir(SKILLS_DIR):
        shutil.copytree(SKILLS_DIR, os.path.join(dest, "skills"), dirs_exist_ok=True)
        items.append({"name": "skills", "size": _dir_size(os.path.join(dest, "skills"))})

    manifest = os.path.join(dest, "README.txt")
    with open(manifest, "w", encoding="utf-8") as f:
        f.write("优墨数据备份\n")
        f.write(f"导出时间：{time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("包含：配置、对话消息、向量库、上传文件、技能库\n")
        f.write("不包含：checkpoints.sqlite（Agent 现场，体积通常很大）\n\n")
        f.write("迁移方法：退出优墨，把本目录内容覆盖到新机器的 userData 目录（Windows 默认 %APPDATA%\\sassy-cat）。\n")
    items.append({"name": "README.txt", "size": os.path.getsize(manifest)})

    return {
        "status": "success",
        "path": dest,
        "items": items,
        "totalSize": sum(int(i.get("size") or 0) for i in items),
        "excluded": ["checkpoints.sqlite"],
    }


@router.post("/export")
async def export_backup(payload: ExportPayload):
    target = os.path.abspath((payload.targetDir or "").strip())
    if not target or not os.path.isdir(target):
        raise HTTPException(status_code=400, detail="请选择一个已存在的备份保存目录")

    # 不能备份到数据目录内部：既避免递归复制，也避免备份文件被下次一起打包
    data_real = os.path.realpath(paths.data_dir())
    target_real = os.path.realpath(target)
    if target_real == data_real or target_real.startswith(data_real + os.sep):
        raise HTTPException(status_code=400, detail="备份目录不能放在应用数据目录内部，请选择其它位置")

    try:
        import asyncio

        result = await asyncio.to_thread(_export_blocking, target)
        logger.info(f"数据备份完成: {result['path']}")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("数据备份失败")
        raise HTTPException(status_code=500, detail=f"备份失败: {e}")
