from langchain.tools import tool, ToolRuntime
from datetime import datetime

from typing import Literal
from tavily import TavilyClient
import os
import re
import sys
import subprocess
import shlex
import shutil
import locale
from pathlib import Path
from agent.models import OwnerProfile
from agent.constant import USER_ID
import config_loader


@tool(description="获取当前时间日期")
def get_date_time():
    now = datetime.now()
    # 输出示例：2026-08-21 15:30:22.123456
    # 转字符串格式化
    return now.strftime("%Y-%m-%d %H:%M:%S")


@tool
def internet_search(
    query: str,
    max_results: int = 5,
    topic: Literal["general", "news", "finance"] = "general",
    include_raw_content: bool = False,
):
    """运行网络搜索"""
    try:
        # 从配置中获取 Tavily API Key（支持热更新）
            cfg = config_loader.current()
            tavily_api_key = cfg.get("agent.tavilyApiKey", "")
            if not tavily_api_key:
                return "错误：未配置 Tavily API Key，请在设置中配置 agent.tavilyApiKey"
            client = TavilyClient(api_key=tavily_api_key)
            return client.search(
                query,
                max_results=max_results,
                include_raw_content=include_raw_content,
                topic=topic,
            )
    except Exception as e:
        return f"查询失败：{e}"

# 项目根目录（builtin_tools.py 位于 python/agent/tools/ 下，向上三级）
PROJECT_ROOT = Path(__file__).resolve().parents[3]

# 工作目录（规范化为绝对路径，即项目根下的 runtime）
work_dir = str(PROJECT_ROOT / "runtime")

# 候选 Python 解释器路径，按优先级排列：.venv 在前，python_env 在后
PYTHON_CANDIDATES = [
    PROJECT_ROOT / ".venv" / "Scripts" / "python.exe",  # Windows 虚拟环境
    PROJECT_ROOT / ".venv" / "bin" / "python",  # POSIX 虚拟环境
    PROJECT_ROOT / "python_env" / "python.exe",  # Windows 嵌入式 Python
    PROJECT_ROOT / "python_env" / "bin" / "python",  # POSIX 嵌入式 Python
]


def _find_python() -> str:
    """查找可用的 Python 解释器：优先 .venv，其次 python_env，均不存在则回退到当前解释器。"""
    for candidate in PYTHON_CANDIDATES:
        if candidate.exists():
            return str(candidate)
    return sys.executable


@tool
def run_python(code: str):
    """使用项目环境（.venv 或 python_env）中的 Python 解释器执行 Python 代码，返回执行结果。"""
    python_exe = _find_python()
    try:
        result = subprocess.run(
            [python_exe, "-c", code],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            cwd=str(PROJECT_ROOT),
        )
    except subprocess.TimeoutExpired:
        return f"执行超时（超过 60 秒），解释器：{python_exe}"
    except Exception as e:
        return f"执行失败：{e}，解释器：{python_exe}"

    output = [f"解释器：python", f"退出码：{result.returncode}"]
    if result.stdout:
        output.append(f"标准输出：\n{result.stdout}")
    if result.stderr:
        output.append(f"错误输出：\n{result.stderr}")
    if not result.stdout and not result.stderr:
        output.append("（无任何输出）")
    return "\n".join(output)


def _convert_virtual_path(segment: str, idx: int) -> list[str]:
    """将单个虚拟路径片段转换为真实路径。

    返回一个列表，因为某些命令（如 pip）可能需要展开为多个片段。

    如果片段以 / 开头且后面跟着的是目录名（不是 - 开头的参数），
    则认为是 FilesystemBackend 的虚拟路径，转换为基于 work_dir 的真实路径。

    例如：
    - `/skills/weather-skill/scripts/fetch_weather.py`
      → `work_dir\\skills\\weather-skill\\scripts\\fetch_weather.py`（Windows）
    - `-v` → `-v`（不变，因为是参数）
    - `echo` → `echo`（不变）
    - `pip` → `[pip绝对路径]` 或 `[python绝对路径, "-m", "pip"]`（回退）
    """
    # 检测 Windows 盘符模式：单个字母 + 冒号（如 C:、D: 等）
    if len(segment) >= 2 and segment[0].isalpha() and segment[1] == ":":
        raise ValueError("Windows环境下不得使用真实盘符作为变量开头")
    
    # 使用 in 操作符正确检查成员关系
    if segment in ("python", "python3") and idx == 0:
        # 使用项目中实际可用的 Python 解释器绝对路径
        return [_find_python()]
    elif segment in ("pip", "pip3") and idx == 0:
        # pip 通常与 Python 解释器在同一目录
        python_exe = Path(_find_python())
        pip_exe = python_exe.parent / ("pip.exe" if os.name == "nt" else "pip")
        if pip_exe.exists():
            return [str(pip_exe)]
        # pip 独立可执行文件不存在，回退到 python -m pip
        return [_find_python(), "-m", "pip"]

    if not segment.startswith("/"):
        return [segment]
    # 去掉前导 /，得到相对路径
    relative_path = segment.lstrip("/")
    # 如果去掉 / 后为空，直接返回原片段
    if not relative_path:
        return [segment]
    # 拼接真实绝对路径
    real_path = os.path.join(work_dir, relative_path)
    # Windows 下将 / 替换为 \\
    if os.name == "nt":
        real_path = real_path.replace("/", "\\")
    return [real_path]


@tool
def run_command(command: list[str], timeout: int = 60):
    """执行系统命令，返回执行结果。

    参数为命令片段数组，例如：["python", "/skills/test.py", "--arg", "value"]
    支持虚拟路径自动转换：数组中以 / 开头的路径片段会自动转换为真实路径。
    不得使用真实路径作为参数传入，比如D://skills, 命令行参数仅支持虚拟环境路径参数，必须是/开头。
    调用如python,pip,java,node,npm,pnpm,go ... 等等开发常用命令时，不要使用绝对路径，只能使用命令本身。如：直接用python,java等，不要使用/home/user/java 这种绝对路径。
    Windows环境下不得使用真实盘符作为变量开头，比如D:/python.exe等。

    参数：
      timeout: 命令执行超时时间（秒），默认 60。执行耗时较长的任务（如安装依赖、编译、下载等）请适当调大。
    """
    # 提前初始化，避免转换阶段抛异常时 except 分支引用未定义变量
    command_str = ""
    try:
        # 遍历每个片段，将虚拟路径转换为真实路径（每个片段可能展开为多个）
        real_command = []
        for idx, seg in enumerate(command):
            real_command.extend(_convert_virtual_path(seg, idx))
        # 拼接为字符串用于 shell 执行（支持 dir、echo 等 shell 内置命令）
        # Windows 用 list2cmdline，POSIX 用 shlex.join，避免跨平台转义语义错乱
        if os.name == "nt":
            command_str = subprocess.list2cmdline(real_command)
        else:
            command_str = shlex.join(real_command)
        # 编码按操作系统活动代码页选择（Windows 常见 GBK/cp936，POSIX 为 UTF-8）
        encoding = locale.getpreferredencoding(False) if os.name == "nt" else "utf-8"
        result = subprocess.run(
            command_str,
            shell=True,
            capture_output=True,
            text=True,
            encoding=encoding,
            errors="replace",
            timeout=timeout,
            cwd=work_dir,
        )
    except subprocess.TimeoutExpired:
        return f"执行超时（超过 {timeout} 秒），命令：{command_str}"
    except Exception as e:
        return f"执行失败：{e}，命令：{command_str}"

    output = [f"退出码：{result.returncode}"]
    if result.stdout:
        output.append(f"标准输出：\n{result.stdout}")
    if result.stderr:
        output.append(f"错误输出：\n{result.stderr}")
    if not result.stdout and not result.stderr:
        output.append("（无任何输出）")
    return "\n".join(output)


# 允许智能体更新用户信息的工具
@tool
def save_user_info(user_info: OwnerProfile, runtime: ToolRuntime) -> str:
    """保存/更新主人画像。只要对话中出现主人的个人信息就应主动调用，无需用户明确要求。

    触发场景示例：
    - 主人自报姓名或称呼："我叫小明"、"叫我老王"
    - 主人表达偏好："我喜欢打篮球"、"我最讨厌香菜"、"别给我推荐咖啡"
    - 主人透露习惯/作息："我经常熬夜"、"我每天早上六点跑步"
    - 主人纠正画像中的旧信息："我现在不喝咖啡了"

    使用规则：本工具为整体覆盖写入。调用前必须把 system prompt 中
    [主人画像] 的已有信息与本次新信息合并成完整画像一并提交，
    未提及的字段保留原值，禁止丢失旧数据。同一轮多条信息合并为一次调用。
    """
    # 访问 store - 与提供给 `create_agent` 的 store 相同
    store = runtime.store
    user_id = USER_ID
    # 在 store 中存储数据 (namespace, key, data)
    # 注意：SqliteStore 序列化要求 JSON 兼容类型，需先 model_dump()
    store.put(("users",), user_id, user_info.model_dump())
    return "用户画像已保存。请在回复中自然地确认已记住（如'本喵记住了'），不要向用户展示工具细节。"


# 技能名规范（agentskills.io）：小写字母/数字，单连字符分隔，不以 - 开头结尾，<=64
_SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
# 单个辅助文件内容上限 1MB，SKILL.md 正文上限 200KB，防止误写巨型文件
MAX_SKILL_FILE_SIZE = 1024 * 1024
MAX_SKILL_MD_SIZE = 200 * 1024

# 技能根目录：runtime/skills（与 skills_api、FilesystemBackend 的 /skills 虚拟目录一致）
SKILLS_ROOT = os.path.join(work_dir, "skills")


def _slugify_skill_name(name: str) -> str:
    """把用户/模型给的名字规范化为合规技能名：小写、空格下划线转 -、去非法字符。"""
    s = (name or "").strip().lower()
    s = re.sub(r"[\s_.]+", "-", s)
    s = re.sub(r"[^a-z0-9-]", "", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s[:64]


def _folded_yaml_text(text: str) -> str:
    """压平为单行并按 72 列折行，供 SKILL.md frontmatter 的 '>' 折叠块使用。"""
    flat = " ".join((text or "").split())
    # YAML 折叠块中标量不能含冒号+空格歧义，简单场景直接保留即可
    lines = []
    cur = ""
    for word in flat.split(" "):
        if cur and len(cur) + 1 + len(word) > 72:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    if cur:
        lines.append(cur)
    return "\n".join(f"  {line}" for line in lines)


def _resolve_skill_file_path(skill_dir: str, rel_path: str) -> str | None:
    """技能内相对路径 -> 绝对路径；非法（越界/绝对路径/盘符）返回 None。"""
    rel = (rel_path or "").replace("\\", "/").strip("/")
    if not rel or rel.startswith("/") or ":" in rel.split("/")[0]:
        return None
    parts = rel.split("/")
    if any(p in ("", ".", "..") for p in parts):
        return None
    target = os.path.realpath(os.path.join(skill_dir, *parts))
    if not target.startswith(os.path.realpath(skill_dir) + os.sep):
        return None
    return target


def _resolve_virtual_src(virtual_path: str) -> str | None:
    """work_dir 下的虚拟路径（/code/xxx.py）-> 真实绝对路径；越界返回 None。"""
    rel = (virtual_path or "").replace("\\", "/").lstrip("/")
    if not rel or ":" in rel.split("/")[0]:
        return None
    parts = rel.split("/")
    if any(p in ("", ".", "..") for p in parts):
        return None
    target = os.path.realpath(os.path.join(work_dir, *parts))
    root = os.path.realpath(work_dir)
    if not target.startswith(root + os.sep):
        return None
    return target


@tool
def create_skill(
    name: str,
    description: str,
    instructions: str,
    files: list[dict] | None = None,
    copies: list[dict] | None = None,
    overwrite: bool = False,
) -> str:
    """创建技能（skill）：把本次对话沉淀出的可复用资产保存为 runtime/skills 下的技能。

    技能 = 一个目录，内含 SKILL.md（frontmatter 描述 + 操作指引正文），
    可选 scripts/（脚本）与 references/（参考资料）等辅助文件。
    之后新会话中 Agent 会自动发现并按 SKILL.md 的指引复用这套流程。

    触发场景：
    - 主人说"把这次的做法/成果保存成技能"、"以后都按这个流程来"
    - 对话中经过多轮指导打磨出了一个有价值的产物或工作流，值得沉淀复用

    参数说明：
    - name: 技能名，仅小写字母/数字/连字符（如 "report-format-skill"）；
      传中文或其它格式会自动尝试转换，转换失败会报错请你重新命名。
    - description: 技能描述（必填），说明"做什么 + 何时触发使用"，
      会被注入系统提示供未来会话判断是否调用本技能，写清触发关键词。
    - instructions: SKILL.md 正文（Markdown），完整描述工作流步骤、
      脚本调用方式、输出示例与注意事项。这是技能的灵魂，务必详尽可执行。
    - files: 可选，辅助文件列表，每项 {"path": 技能内相对路径, "content": 文本内容}，
      如 {"path": "scripts/run.py", "content": "..."}。禁止二进制与越界路径。
    - copies: 可选，把本次对话在虚拟环境中已生成的产物复制进技能，
      每项 {"src": 虚拟路径, "dest": 技能内相对路径}，
      如 {"src": "/code/clean_data.py", "dest": "scripts/clean_data.py"}。
      src 必须是 / 开头、位于虚拟环境内的路径（如 /code、/data、/tmp 下的文件）。
    - overwrite: 同名技能已存在时是否覆盖（默认 False 直接拒绝）。
      覆盖时旧版本自动备份为 "{name}.bak-时间戳"。

    返回创建结果。注意：新技能在**新会话**中才会被加载，当前会话不会立即生效。
    """
    # ---------- 名称规范化与校验 ----------
    slug = _slugify_skill_name(name)
    if not slug or not _SKILL_NAME_RE.match(slug) or len(slug) > 64:
        return (
            f"错误：技能名 {name!r} 无法转换为合法名称。"
            "请使用小写字母/数字/单个连字符，如 'weekly-report-skill'。"
        )

    description = (description or "").strip()
    if not description:
        return "错误：description 不能为空，需说明技能做什么、何时使用。"
    if len(description) > 1024:
        description = description[:1024]

    # ---------- 目标目录与冲突处理 ----------
    skill_dir = os.path.realpath(os.path.join(SKILLS_ROOT, slug))
    if not skill_dir.startswith(os.path.realpath(SKILLS_ROOT) + os.sep):
        return "错误：非法的技能名称。"
    backup_note = ""
    if os.path.exists(skill_dir):
        if not overwrite:
            return (
                f"错误：技能「{slug}」已存在。若确要替换，请传 overwrite=true"
                "（旧版本会自动备份）。"
            )
        backup = f"{skill_dir}.bak-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        try:
            os.rename(skill_dir, backup)
            backup_note = f"（旧版本已备份为 {os.path.basename(backup)}）"
        except OSError as e:
            return f"错误：备份旧技能失败：{e}"

    # ---------- 组装 SKILL.md ----------
    body = (instructions or "").strip()
    if not body:
        body = (
            f"# {slug}\n\n"
            f"## 使用说明\n\n{description}\n\n"
            "TODO：补充详细工作流步骤与注意事项。\n"
        )
    if len(body) > MAX_SKILL_MD_SIZE:
        return f"错误：instructions 过大（{len(body)} 字符，上限 {MAX_SKILL_MD_SIZE}）。"
    skill_md = (
        "---\n"
        f"name: {slug}\n"
        "description: >\n"
        f"{_folded_yaml_text(description)}\n"
        "---\n\n"
        f"{body}\n"
    )

    # ---------- 预校验所有辅助文件，全部合法才落盘 ----------
    staged: list[tuple[str, bytes]] = []  # (绝对路径, 内容)
    try:
        for item in files or []:
            rel = (item or {}).get("path", "")
            content = (item or {}).get("content", "")
            if not isinstance(content, str):
                return f"错误：files 中 {rel!r} 的 content 必须是文本字符串。"
            target = _resolve_skill_file_path(skill_dir, rel)
            if target is None:
                return f"错误：files 路径非法（越界/绝对路径/盘符）：{rel!r}"
            data = content.encode("utf-8")
            if len(data) > MAX_SKILL_FILE_SIZE:
                return f"错误：文件 {rel!r} 超过 1MB 上限。"
            staged.append((target, data))

        for item in copies or []:
            src = (item or {}).get("src", "")
            rel = (item or {}).get("dest", "")
            real_src = _resolve_virtual_src(src)
            if real_src is None:
                return f"错误：copies.src 必须是虚拟环境内的合法路径（/ 开头）：{src!r}"
            if not os.path.isfile(real_src):
                return f"错误：copies.src 指向的文件不存在：{src!r}"
            target = _resolve_skill_file_path(skill_dir, rel)
            if target is None:
                return f"错误：copies.dest 路径非法：{rel!r}"
            with open(real_src, "rb") as f:
                data = f.read()
            if len(data) > MAX_SKILL_FILE_SIZE:
                return f"错误：复制文件 {src!r} 超过 1MB 上限。"
            staged.append((target, data))
    except Exception as e:
        return f"错误：解析技能文件参数失败：{e}"

    # ---------- 写盘（失败回滚半成品目录） ----------
    written = []
    try:
        os.makedirs(SKILLS_ROOT, exist_ok=True)
        os.makedirs(skill_dir, exist_ok=True)
        with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write(skill_md)
        written.append("SKILL.md")
        for target, data in staged:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as f:
                f.write(data)
            written.append(os.path.relpath(target, skill_dir).replace("\\", "/"))
    except OSError as e:
        shutil.rmtree(skill_dir, ignore_errors=True)
        return f"错误：写入技能失败，已回滚：{e}"

    return (
        f"技能「{slug}」已创建成功{backup_note}。"
        f"位置：/skills/{slug}/，文件：{', '.join(written)}。"
        "提醒主人：新技能会在**下一次新会话**中自动生效并可被调用。"
        "请在回复中自然地确认技能已保存（如'本喵已经把这套流程存成技能了'），不要向用户展示工具细节。"
    )