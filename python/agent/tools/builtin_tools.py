from langchain.tools import tool, ToolRuntime
from datetime import datetime

from typing import Literal
from tavily import TavilyClient
import hashlib
import os
import re
import sys
import threading
import uuid
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


# Windows 命令行开关：/c、/k、/A、/c:xxx、/TS、/help、/? ...
# 这些片段虽然以 / 开头，但绝不是虚拟路径，必须原样保留，
# 否则 ["cmd", "/c", ...] 会被改写成 cmd <work_dir>\c，cmd 进入交互式 shell。
_WIN_SWITCH_RE = re.compile(r"^/[?A-Za-z](?::.*)?$")
_WIN_UPPER_SWITCH_RE = re.compile(r"^/[A-Z][A-Z0-9]{1,4}$")
# 常见长开关名（含 start 的 /wait、/min、/max、/node 等），避免被误当虚拟路径
_LONG_SWITCH_NAMES = {
    "help", "version", "quiet", "silent", "yes", "no", "force", "verbose",
    "wait", "min", "max", "node", "affinity", "low", "normal", "high",
    "realtime", "abovenormal", "belownormal", "separate", "shared",
}


def _looks_like_switch(segment: str) -> bool:
    """判断片段是命令行开关（/c、/A、/TS、/help、/?）而非虚拟路径。"""
    if not segment.startswith("/") or segment.startswith("//"):
        return False
    if segment.startswith("/?") or _WIN_SWITCH_RE.fullmatch(segment):
        return True
    body = segment[1:]
    if "/" in body or "\\" in body:
        return False
    if _WIN_UPPER_SWITCH_RE.fullmatch(segment):
        return True
    return body.lower() in _LONG_SWITCH_NAMES


def _convert_virtual_path(segment: str, idx: int, prev: str | None = None) -> list[str]:
    """将单个虚拟路径片段转换为真实路径。

    返回一个列表，因为某些命令（如 pip）可能需要展开为多个片段。

    如果片段以 / 开头且后面跟着的是目录名（不是 - 开头的参数），
    则认为是 FilesystemBackend 的虚拟路径，转换为基于 work_dir 的真实路径。
    但命令行开关（/c、/k、/A、/TS、/help、/?）必须原样保留，
    否则 cmd /c 会被改写成 cmd <work_dir>\\c，cmd 进入交互式 shell、打印版本
    横幅后立即退出（退出码 0，但命令实际上从未执行）。
    相对路径（./x、../x）统一规范化为基于 work_dir 的绝对路径，
    避免 start/浏览器等宿主程序按自己的当前目录去解析。

    例如：
    - `/skills/weather-skill/scripts/fetch_weather.py`
      → `work_dir\\skills\\weather-skill\\scripts\\fetch_weather.py`（Windows）
    - `/c` → `/c`（不变，是 cmd 开关）
    - `./code/index.html` → `work_dir\\code\\index.html`（规范化为绝对路径）
    - `-v` → `-v`（不变，因为是参数）
    - `echo` → `echo`（不变）
    - `pip` → `[pip绝对路径]` 或 `[python绝对路径, "-m", "pip"]`（回退）

    参数 prev 为前一片段：python/pip 出现在数组首位，或紧跟 cmd /c 之后，
    都视为“命令名位置”，会被替换为项目解释器的绝对路径
    （避免 pyenv 之类 .bat 垫片在多层 cmd 下把参数当批处理语法解析）。
    """
    # 检测 Windows 盘符模式：单个字母 + 冒号（如 C:、D: 等）
    # if len(segment) >= 2 and segment[0].isalpha() and segment[1] == ":":
    #     raise ValueError("Windows环境下不得使用真实盘符作为变量开头")
    
    # 命令名位置：数组首位，或紧跟 cmd /c（/k）之后
    at_command_position = idx == 0 or (
        prev is not None and (prev.lower() in ("/c", "/k") or _is_cmd_program(prev))
    )
    # 使用 in 操作符正确检查成员关系
    if segment in ("python", "python3") and at_command_position:
        # 使用项目中实际可用的 Python 解释器绝对路径
        return [_find_python()]
    elif segment in ("pip", "pip3") and at_command_position:
        # pip 通常与 Python 解释器在同一目录
        python_exe = Path(_find_python())
        pip_exe = python_exe.parent / ("pip.exe" if os.name == "nt" else "pip")
        if pip_exe.exists():
            return [str(pip_exe)]
        # pip 独立可执行文件不存在，回退到 python -m pip
        return [_find_python(), "-m", "pip"]

    # 开关参数优先判断，绝不能当作虚拟路径拼接
    if _looks_like_switch(segment):
        return [segment]
    # 相对路径规范化为 work_dir 下的绝对路径（start、浏览器等靠此定位文件）
    if segment.startswith(("./", "../", ".\\", "..\\")):
        return [os.path.normpath(os.path.join(work_dir, segment))]
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


def _is_cmd_program(segment: str) -> bool:
    """判断片段是否为 cmd / cmd.exe（兼容绝对路径写法）。"""
    return os.path.basename(segment).lower() in ("cmd", "cmd.exe")


def _comspec() -> str:
    """取 cmd.exe 的完整路径（COMSPEC 缺失时回退到系统目录）。"""
    comspec = os.environ.get("COMSPEC")
    if comspec:
        return comspec
    system_root = os.environ.get("SystemRoot") or r"C:\Windows"
    return os.path.join(system_root, "System32", "cmd.exe")


def _validate_windows_command(real_command: list[str]) -> str | None:
    """Windows 下对 cmd 调用做前置校验，返回错误说明（None 表示可以执行）。

    cmd 不带 /c 时会进入交互式 shell：打印版本横幅后立刻退出，
    退出码是 0，但期望的命令从未执行——这是最隐蔽的“假成功”。
    """
    if os.name != "nt" or not real_command:
        return None
    if not _is_cmd_program(real_command[0]):
        return None
    lowered = [seg.lower() for seg in real_command[1:]]
    if "/c" in lowered:
        return None
    if "/k" in lowered:
        return (
            "命令未执行：本工具是非交互环境，cmd /k 会保留 shell 并等待输入，拿不到结果。"
            '请改用 /c（执行后退出），例如 ["cmd", "/c", "dir"]。'
        )
    return (
        "命令未执行：Windows 下调用 cmd 必须紧跟 /c（执行后退出）开关。"
        "当前调用缺少 /c，cmd 会进入交互式 shell：打印版本横幅后立即退出，"
        "退出码虽然是 0，但命令实际上没有执行。"
        '正确写法示例：["cmd", "/c", "dir", "/skills"]、'
        '["cmd", "/c", "start", "", "/code/index.html"]。'
    )


# `start` 打开本地文件时用于识别“文件类参数”的扩展名
_START_TARGET_EXT_RE = re.compile(
    r"\.(?:html?|xhtml|pdf|txt|md|json|csv|log|xml|png|jpe?g|gif|svg|webp|bmp"
    r"|mp[34]|wav|docx?|xlsx?|pptx?)$",
    re.IGNORECASE,
)


def _needs_start_title(segment: str) -> bool:
    """判断 `start` 之后的首个参数是否会被 cmd 误当作窗口标题。"""
    stripped = segment.strip()
    bare = stripped.strip("\"'")
    if not bare:
        return False
    # 带引号时，旧版 cmd 会把第一个带引号参数当作标题
    if stripped != bare:
        return True
    if " " in bare or "\t" in bare:
        return True
    if bare.startswith(("/", "\\", "./", "../", ".\\", "..\\", "~")):
        return True
    if re.match(r"^[A-Za-z]:[\\/]", bare):
        return True
    return bool(_START_TARGET_EXT_RE.search(bare))


def _fix_start_title(real_command: list[str]) -> list[str]:
    """`start` 后紧跟路径/带引号参数时自动补一个空标题 ""。

    cmd 的 start 语法是 `start ["title"] [/switch] program [args]`：
    若省略标题而第一个参数带引号或形如路径，cmd 会把它当成窗口标题，
    结果是什么都没打开（退出码仍是 0）。
    """
    if os.name != "nt":
        return real_command
    fixed: list[str] = []
    for i, seg in enumerate(real_command):
        fixed.append(seg)
        if seg.lower() != "start" or i + 1 >= len(real_command):
            continue
        nxt = real_command[i + 1]
        if not nxt or _looks_like_switch(nxt):
            continue
        if _needs_start_title(nxt):
            fixed.append("")
    return fixed


def _looks_like_local_file_arg(segment: str) -> bool:
    """判断 `start` 之后的某个片段是否指向本地文件（排除 URL、开关、程序名）。"""
    bare = segment.strip().strip("\"'")
    if not bare or "://" in bare:
        return False
    if any(ch in bare for ch in "%*?"):  # 含环境变量/通配符，无法静态校验
        return False
    if _looks_like_switch(bare) or bare.startswith("-"):
        return False
    if re.match(r"^[A-Za-z]:[\\/]", bare) or os.path.isabs(bare):
        return True
    if bare.startswith(("/", "\\", "./", "../", ".\\", "..\\")):
        return True
    if "\\" in bare or "/" in bare:
        return True
    return bool(_START_TARGET_EXT_RE.search(bare))


def _check_start_targets(real_command: list[str]) -> str | None:
    """`start` 打开本地文件时先确认文件存在，避免退出码 0 的假成功。"""
    if os.name != "nt":
        return None
    for i, seg in enumerate(real_command):
        if seg.lower() != "start":
            continue
        for cand in real_command[i + 1:]:
            # start 的开关（/wait、/min、/B 等）不是文件路径，跳过
            if cand.startswith("/") and not cand.startswith("//"):
                continue
            if not _looks_like_local_file_arg(cand):
                continue
            raw = cand.strip().strip("\"'")
            target = os.path.normpath(raw if os.path.isabs(raw) else os.path.join(work_dir, raw))
            if not os.path.exists(target):
                return (
                    f"命令未执行：`start` 要打开的本地文件不存在 —— {raw}\n"
                    f"解析后的真实路径：{target}\n"
                    f"提示：虚拟路径以工作目录 {work_dir} 为根"
                    f"（/skills/... → {os.path.join(work_dir, 'skills')}\\...）。"
                    "请先用 list_files / read_file 确认真实位置后重试。"
                )
    return None


def _is_start_command(real_command: list[str]) -> bool:
    """命令中是否包含 start（用于结果说明：start 不等待目标程序）。"""
    return any(seg.lower() == "start" for seg in real_command)


def _windows_console_codepage() -> str | None:
    """取 Windows 控制台（OEM）代码页，cmd 内置命令的输出字节就是用它编码的。"""
    if os.name != "nt":
        return None
    try:
        import ctypes

        oem = int(ctypes.windll.kernel32.GetOEMCP())
        return f"cp{oem}" if oem else None
    except Exception:
        return None


def _decode_candidates() -> list[str]:
    """待尝试的解码方案，按可靠性排序并去重。

    本进程常被注入 PYTHONUTF8=1 / PYTHONIOENCODING=utf-8，
    此时 locale.getpreferredencoding() 会返回 utf-8，
    而 cmd 的 dir/echo 等输出仍是 GBK/cp936 字节，直接用 locale 解码会得到一串
    替换字符（乱码）。所以必须显式把系统控制台代码页作为兜底候选。
    """
    names = [
        "utf-8",  # 现代 CLI、被 PYTHONUTF8=1 影响的子进程
        _windows_console_codepage(),  # cmd 内置命令（dir/echo/type...）
        locale.getpreferredencoding(False),
        "gbk",
    ]
    seen: set[str] = set()
    result: list[str] = []
    for name in names:
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(name)
    return result


def _decode_output(data: bytes | None) -> str:
    """解码子进程输出：UTF-8 严格优先，失败回退系统控制台代码页。"""
    if not data:
        return ""
    candidates = _decode_candidates()
    for enc in candidates:
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    # 混合编码等极端情况：用最可能的代码页做替换解码，保证不抛异常
    fallback = _windows_console_codepage() or "utf-8"
    try:
        return data.decode(fallback, errors="replace")
    except LookupError:
        return data.decode("utf-8", errors="replace")


@tool
def run_command(command: list[str], timeout: int = 60):
    """执行系统命令，返回执行结果。

    参数为命令片段数组，例如：["python", "/skills/test.py", "--arg", "value"]
    支持虚拟路径自动转换：数组中以 / 开头的路径片段会自动转换为真实路径。
    不得使用真实路径作为参数传入，比如D://skills, 命令行参数仅支持虚拟环境路径参数，必须是/开头。
    调用如python,pip,java,node,npm,pnpm,go ... 等等开发常用命令时，不要使用绝对路径，只能使用命令本身。如：直接用python,java等，不要使用/home/user/java 这种绝对路径。
    Windows环境下不得使用真实盘符作为变量开头，比如D:/python.exe等。

    当前平台为 Windows，执行细节（正常写法不受影响）：
    1. 本工具以原生 argv 执行命令，不做额外的 shell 包装，参数与引号原样传递
       （["python", "-c", "print(1)"] 这类带引号参数不会再被吞掉）。
    2. 执行 cmd 内置命令（dir/echo/type/copy/start 等）请写成 ["cmd", "/c", ...]，
       /c 表示执行完就退出；缺少 /c 的调用会被直接拒绝，因为 cmd 会进入交互式
       shell、只打印版本横幅就退出（退出码 0 但没有执行任何命令）。
       不带 cmd 前缀的内置命令（如 ["dir", "/skills"]）会自动补上 cmd /c。
       /c、/k、/A、/wait 这类开关会原样保留，不会被当虚拟路径。
    3. 用浏览器/默认程序打开本地文件，用 start 并紧跟一个空标题 ""，例如：
       ["cmd", "/c", "start", "", "/code/index.html"]
       否则 cmd 会把第一个参数当成窗口标题，结果什么都没打开。工具会自动补空标题，
       并在打开前校验文件是否存在（不存在直接报错，不会假成功）。
    4. 虚拟路径以工作目录为根：/code/x.html → <工作目录>\\code\\x.html。
       子代理（dsh）的产物在 /.dsh/workspace/ 下，例如 /.dsh/workspace/index.html。

    参数：
      timeout: 命令执行超时时间（秒），默认 60。执行耗时较长的任务（如安装依赖、编译、下载等）请适当调大。
    """
    # 提前初始化，避免转换阶段抛异常时 except 分支引用未定义变量
    command_str = ""
    try:
        # 遍历每个片段，将虚拟路径转换为真实路径（每个片段可能展开为多个）
        real_command = []
        for idx, seg in enumerate(command):
            real_command.extend(
                _convert_virtual_path(seg, idx, command[idx - 1] if idx else None)
            )
        # cmd 缺少 /c 时是“退出码 0 但什么都没执行”的假成功，先拦下来
        problem = _validate_windows_command(real_command)
        if problem:
            return problem
        # start 后直接跟路径/带引号参数时补空标题，避免被当成窗口标题
        real_command = _fix_start_title(real_command)
        # start 打开的本地文件先校验存在性，避免“以为打开了其实没有”
        problem = _check_start_targets(real_command)
        if problem:
            return problem
        # Windows 用 list2cmdline（仅用于日志/回显），POSIX 用 shlex.join
        if os.name == "nt":
            command_str = subprocess.list2cmdline(real_command)
        else:
            command_str = shlex.join(real_command)
        # 输出按字节捕获，再由 _decode_output 择优解码（UTF-8 优先，回退系统代码页）
        if os.name == "nt":
            # 不用 shell=True：Python 会把命令包成 cmd.exe /c "<命令>"，
            # 当命令含引号（如 ["python", "-c", "print(1)"]）时会被 cmd 的引号剥离
            # 规则弄坏，表现为“退出码 0 但没有任何输出”；命令本身以 cmd 开头时
            # 还会多传一个引号（echo hello 变成 hello"）。这里改用原生 argv：
            # cmd 调用直接透传，其余命令显式套一层 cmd /c，既保住 dir/echo/start
            # 等内置命令能力，又保证参数与引号原样传递。
            if _is_cmd_program(real_command[0]):
                run_args: list[str] | str = list(real_command)
            else:
                run_args = [_comspec(), "/c", *real_command]
            result = subprocess.run(
                run_args,
                shell=False,
                capture_output=True,
                timeout=timeout,
                cwd=work_dir,
                # 非交互环境：显式关闭 stdin，避免误起的交互式 shell 挂着等输入
                stdin=subprocess.DEVNULL,
            )
        else:
            result = subprocess.run(
                command_str,
                shell=True,
                capture_output=True,
                timeout=timeout,
                cwd=work_dir,
                stdin=subprocess.DEVNULL,
            )
    except subprocess.TimeoutExpired:
        return f"执行超时（超过 {timeout} 秒），命令：{command_str}"
    except Exception as e:
        return f"执行失败：{e}，命令：{command_str}"

    stdout = _decode_output(result.stdout)
    stderr = _decode_output(result.stderr)
    output = [f"退出码：{result.returncode}"]
    if stdout:
        output.append(f"标准输出：\n{stdout}")
    if stderr:
        output.append(f"错误输出：\n{stderr}")
    if not stdout and not stderr:
        output.append("（无任何输出）")
    if result.returncode == 0 and _is_start_command(real_command):
        output.append("（start 已把目标交给系统打开：退出码 0 只表示启动请求成功，不代表目标程序已完成）")
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


# ---------------------------------------------------------------------------
# 任务清单（todo）：把复杂任务拆解成有序子任务并跟踪执行进度
#
# 定位：这是智能体**自己**的「任务拆解 + 进度跟踪」工具，不是帮主人记备忘；
# 复杂任务先拆解成子任务清单，再逐步执行、逐步勾选，避免漏步骤与中途跑偏。
# 一个复杂任务一份文件：{work_dir}/todo/<thread_id>-<task_key>.md
# （thread_id 作文件名前缀，会话之间天然隔离；task_key 由任务名派生）。
# 文件结构（正文里的非条目行会原样保留，兼容手工编辑）：
#
#   ---
#   session: session_xxx
#   task: 整理下载目录并生成索引
#   task_key: zheng-li-xia-zai-mu-lu
#   created_at: 2026-09-01 10:00:00
#   updated_at: 2026-09-01 10:05:00
#   total: 3
#   done: 1
#   pending: 2
#   ---
#
#   # 任务拆解：整理下载目录并生成索引
#
#   - [x] t-1a2b3c 统计下载目录里的文件类型与数量
#   - [ ] t-4d5e6f 按类型建子目录并归类
#   - [ ] t-7a8b9c 生成索引 markdown 并核对结果
# ---------------------------------------------------------------------------

# 清单根目录：runtime/todo（即虚拟环境中的 /todo）
TODO_ROOT = os.path.join(work_dir, "todo")

# 会话 id -> 文件名安全字符（thread_id 可能含 / : 空格等非法字符）
_TODO_SESSION_SAFE_RE = re.compile(r"[^0-9A-Za-z._-]")
# Windows 保留设备名不能直接当文件名
_TODO_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
# 条目行格式：- [ ] t-1a2b3c 子任务内容（顺序即执行顺序，不设优先级）
_TODO_ITEM_RE = re.compile(
    r"^\s*[-*]\s+\[(?P<mark>[ xX])\]\s+(?P<id>t-[0-9a-z]{4,12})\s+(?P<content>\S.*)$"
)
# 任务名长度上限
MAX_TODO_TASK_LEN = 100
# 单条子任务内容长度上限（清单会被整段读回上下文，过长会挤占预算）
MAX_TODO_CONTENT = 500
# 单次调用最多创建/操作的条数
MAX_TODO_BATCH = 50
# 同一进程内串行化清单写操作，避免并发工具调用互相覆盖
_TODO_LOCK = threading.RLock()


def _todo_now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _todo_session_key(runtime: "ToolRuntime | None") -> str:
    """从 ToolRuntime 取当前会话标识（langchain thread_id），清洗为文件名安全字符。

    拿不到 thread_id 时退化为 default-session，保证工具本身不会异常失败。
    """
    config = getattr(runtime, "config", None) or {}
    configurable = config.get("configurable") or {}
    raw = str(configurable.get("thread_id") or "").strip()
    safe = _TODO_SESSION_SAFE_RE.sub("-", raw).strip("-.")
    if not safe:
        safe = "default-session"
    if safe.upper() in _TODO_RESERVED_NAMES:
        safe = f"session-{safe}"
    return safe[:80]


def _todo_task_key(title: str) -> str:
    """任务名 -> 文件名安全 key；中文等非 ASCII 任务名回退到稳定短哈希。

    同一任务名（同一会话内）始终映射到同一个 key，因此可以反复定位同一份清单。
    """
    text = (title or "").strip()
    slug = re.sub(r"[\s_]+", "-", text.lower())
    slug = re.sub(r"[^0-9a-z-]", "", slug)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    if slug:
        return slug[:60]
    return "task-" + hashlib.md5(text.encode("utf-8")).hexdigest()[:8]


def _todo_file_path(session_key: str, task_key: str) -> str | None:
    """(会话, 任务) -> 清单文件绝对路径；越界（理论上不会发生）返回 None。"""
    root = os.path.realpath(TODO_ROOT)
    path = os.path.realpath(os.path.join(root, f"{session_key}-{task_key}.md"))
    if not path.startswith(root + os.sep):
        return None
    return path


def _new_todo_id(used: set) -> str:
    """生成不与清单内已有条目冲突的条目 id（形如 t-1a2b3c）。"""
    while True:
        tid = "t-" + uuid.uuid4().hex[:6]
        if tid not in used:
            return tid


def _list_session_todo_files(session_key: str) -> list[str]:
    """列出本会话的全部任务清单文件（按 updated_at 倒序）。"""
    if not os.path.isdir(TODO_ROOT):
        return []
    prefix = f"{session_key}-"
    files = []
    for name in os.listdir(TODO_ROOT):
        full = os.path.join(TODO_ROOT, name)
        if name.startswith(prefix) and name.endswith(".md") and os.path.isfile(full):
            files.append(full)
    def _sort_key(p: str) -> tuple:
        try:
            mtime = os.path.getmtime(p)
        except OSError:
            mtime = 0.0
        # updated_at 只精确到秒，同一秒内多次写入用 mtime 兜底排序
        return (_read_todo(p)[0].get("updated_at") or "", mtime)

    files.sort(key=_sort_key, reverse=True)
    return files


def _find_todo_file(session_key: str, task: str) -> str | None:
    """定位某任务的清单文件：先按 task_key 命中；再按 frontmatter 里的 task 名匹配
    （兼容直接传中文任务名或文件里的 title）。"""
    task = (task or "").strip()
    if not task:
        return None
    path = _todo_file_path(session_key, _todo_task_key(task))
    if path and os.path.isfile(path):
        return path
    for candidate in _list_session_todo_files(session_key):
        meta, _entries, _raw = _read_todo(candidate)
        title = (meta.get("task") or "").strip()
        if title and (title == task or title.lower() == task.lower()):
            return candidate
    return None


def _todo_task_choices(session_key: str, limit: int = 8) -> str:
    """本会话已有任务清单的概览，用于任务名/id 找不到时的纠错提示。"""
    files = _list_session_todo_files(session_key)
    if not files:
        return "当前会话还没有任何任务清单。"
    parts = []
    for path in files[:limit]:
        meta, entries, _raw = _read_todo(path)
        items = _todo_items(entries)
        done = sum(1 for e in items if e["done"])
        parts.append(f"「{meta.get('task') or os.path.basename(path)}」（{done}/{len(items)}）")
    return "当前会话的清单：" + "；".join(parts)


def _split_todo_front_matter(text: str) -> tuple[dict, list[str]]:
    """拆出 YAML frontmatter（仅解析简单 k: v）与正文行；无 frontmatter 时 meta 为空。"""
    lines = (text or "").splitlines()
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                meta: dict[str, str] = {}
                for line in lines[1:i]:
                    key, _, value = line.partition(":")
                    if key.strip():
                        meta[key.strip()] = value.strip()
                return meta, lines[i + 1:]
    return {}, lines


def _parse_todo_body(body_lines: list[str]) -> list[dict]:
    """正文行 -> 条目序列；无法识别的行原样保留（raw），兼容主人手工编辑。"""
    entries: list[dict] = []
    for line in body_lines:
        m = _TODO_ITEM_RE.match(line)
        if not m:
            entries.append({"type": "raw", "text": line})
            continue
        entries.append({
            "type": "item",
            "id": m.group("id"),
            "done": m.group("mark").lower() == "x",
            "content": m.group("content").strip(),
        })
    # 首尾空行由渲染逻辑统一生成，这里丢掉，避免每次写回都多堆一行
    while entries and entries[0]["type"] == "raw" and not entries[0]["text"].strip():
        entries.pop(0)
    while entries and entries[-1]["type"] == "raw" and not entries[-1]["text"].strip():
        entries.pop()
    return entries


def _render_todo_entry(entry: dict) -> str:
    if entry["type"] == "raw":
        return entry["text"]
    mark = "x" if entry["done"] else " "
    return f"- [{mark}] {entry['id']} {entry['content']}"


def _render_todo_markdown(entries: list[dict], meta: dict) -> str:
    """条目序列 -> 完整清单文件内容（frontmatter + 正文）。"""
    items = _todo_items(entries)
    done = sum(1 for e in items if e["done"])
    lines = [
        "---",
        f"session: {meta.get('session', '')}",
        f"task: {meta.get('task', '')}",
        f"task_key: {meta.get('task_key', '')}",
        f"created_at: {meta.get('created_at') or _todo_now()}",
        f"updated_at: {_todo_now()}",
        f"total: {len(items)}",
        f"done: {done}",
        f"pending: {len(items) - done}",
        "---",
        "",
    ]
    has_heading = any(
        e["type"] == "raw" and e["text"].lstrip().startswith("#") for e in entries
    )
    if not has_heading:
        lines += [f"# 任务拆解：{meta.get('task', '')}", ""]
    lines += [_render_todo_entry(e) for e in entries]
    return "\n".join(lines).rstrip("\n") + "\n"


def _read_todo(path: str) -> tuple[dict, list[dict], str]:
    """读取清单，返回 (frontmatter, 条目序列, 原始文本)；文件不存在时返回空清单。"""
    if not os.path.isfile(path):
        return {"created_at": _todo_now()}, [], ""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        raw = f.read()
    meta, body = _split_todo_front_matter(raw)
    if not meta.get("created_at"):
        meta["created_at"] = _todo_now()
    return meta, _parse_todo_body(body), raw


def _save_todo_file(path: str, entries: list[dict], meta: dict) -> str | None:
    """原子写回清单（先写临时文件再替换，避免中断留下半截文件）；失败返回错误文案。"""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        text = _render_todo_markdown(entries, meta)
        tmp = f"{path}.tmp-{uuid.uuid4().hex[:8]}"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except OSError as e:
        return f"错误：写入任务清单失败：{e}"
    return None


def _todo_items(entries: list[dict]) -> list[dict]:
    return [e for e in entries if e["type"] == "item"]


def _todo_summary(entries: list[dict]) -> str:
    items = _todo_items(entries)
    done = sum(1 for e in items if e["done"])
    return f"进度 {done}/{len(items)}，未完成 {len(items) - done} 项"


def _todo_id_hint(items: list[dict]) -> str:
    """id 找不到时给出清单里的现有条目，便于模型自我修正。"""
    if not items:
        return "当前清单没有任何条目。"
    preview = "、".join(f"{e['id']}（{e['content'][:12]}）" for e in items[:6])
    more = "…" if len(items) > 6 else ""
    return f"当前条目：{preview}{more}（可调用 get_todo 查看全部）。"


@tool
def create_todo(
    runtime: ToolRuntime,
    task: str,
    items: list[str],
    overwrite: bool = False,
) -> str:
    """复杂任务的第一步动作：立刻把任务拆解成有序子任务清单（todo），再逐步执行。

    这是助手**自己的任务规划工具，不是可选项**。命中以下任一条就必须先调用本工具
    （先建清单，再动其它工具）：
    - 预计要 3 次以上工具调用（读/写多个文件、跑命令、检索、生成产物后再验证……）
    - 会碰到 2 个以上文件，或需要"先看现状再改造"
    - 产出要经过"生成→运行/检查验证"才能交付（写代码/脚本、做表格/文档/页面/图片）
    - 主人一句话里含多件事，或需跨多轮才能做完
    只有"一两次工具调用就能直接给出答案"的简单事不要拆解，直接做。

    使用纪律：
    - 不要问主人"要不要我列个清单"：清单是内部工作台，直接建好接着干
      （本工具写的是 /todo 下的内部清单文件，属低危操作，无需用户确认）。
    - 拆完立刻执行第 1 条子任务；每完成一条**立刻** edit_todo(action="done")，
      不要攒到最后一起勾。

    参数说明：
    - task: 任务名，简短可读（如 "整理下载目录并生成索引"）。同一会话里，同一任务名
      对应同一份清单文件；不同任务互相独立。
    - items: 子任务列表，**按执行顺序**排列，建议 3~8 条，粒度要求：
      - 一条只做一件可独立验证的事，写完能照着直接动手（如 "按扩展名把文件移动到 music/images/docs 三个子目录"）；
      - 不要把多个文件/多个动作塞进一条（"分析 a.py、b.py、c.py" 应按文件或模块拆开）；
      - 不要写"深入了解 / 分析一下 / 处理剩余问题"这类没有动作与产出定义的条目，每条要能回答"做完的标准是什么"；
      - 尽量带上关键输入/产出（文件名、目录、要生成的产物），别写"按上面说的做"。
      拆得太粗（只列 1~2 条空泛条目）等于没拆，会被判为不合格。
    - overwrite: 同名任务清单已存在时是否重建（默认 False，会直接拒绝，避免误删已有进度）；
      确需推翻重排时才传 True（旧清单被覆盖）。

    返回清单概况与每条子任务的 id（形如 t-1a2b3c）；之后用 edit_todo 按 id 勾选完成。
    本工具只做任务拆解与进度记录，不负责定时提醒（"到点提醒我"要用 create_reminder）。
    """
    task = " ".join((task or "").split())
    if not task:
        return "错误：task 不能为空，请给出简短的任务名。"
    if len(task) > MAX_TODO_TASK_LEN:
        task = task[:MAX_TODO_TASK_LEN]

    raw_items = items if isinstance(items, list) else ([items] if items else [])
    cleaned: list[str] = []
    for item in raw_items:
        if isinstance(item, dict):
            item = item.get("content") or item.get("task") or ""
        text = " ".join(str(item or "").split())
        if not text:
            continue
        if len(text) > MAX_TODO_CONTENT:
            return (
                f"错误：单条子任务过长（{len(text)} 字符，上限 {MAX_TODO_CONTENT}），"
                f"请拆成两条：{text[:40]}…"
            )
        cleaned.append(text)
    if not cleaned:
        return "错误：items 不能为空，请给出至少 1 条可执行的子任务。"
    if len(cleaned) > MAX_TODO_BATCH:
        return f"错误：单次最多创建 {MAX_TODO_BATCH} 条子任务，收到 {len(cleaned)} 条。"

    session_key = _todo_session_key(runtime)
    task_key = _todo_task_key(task)
    path = _todo_file_path(session_key, task_key)
    if path is None:
        return "错误：会话 id 非法，无法定位任务清单文件。"

    with _TODO_LOCK:
        old_meta = _read_todo(path)[0] if os.path.isfile(path) else {}
        if old_meta and not overwrite:
            return (
                f"任务「{old_meta.get('task') or task}」已有拆解清单"
                f"（{_todo_summary(_read_todo(path)[1])}），未做改动。"
                '若只是新增步骤，用 edit_todo 的 action="add"；'
                "若确实要重新拆解，请传 overwrite=true。"
            )
        meta = {
            "session": session_key,
            "task": task,
            "task_key": task_key,
            "created_at": old_meta.get("created_at") or _todo_now(),
        }
        entries: list[dict] = []
        used: set = set()
        created = []
        for text in cleaned:
            tid = _new_todo_id(used)
            used.add(tid)
            entries.append({"type": "item", "id": tid, "done": False, "content": text})
            created.append(f"- {tid} {text}")
        err = _save_todo_file(path, entries, meta)
        if err:
            return err

    return (
        f"任务「{task}」已拆解为 {len(cleaned)} 步（清单文件 {os.path.basename(path)}）：\n"
        + "\n".join(created)
        + f"\n现在立刻开始执行第 1 步：{cleaned[0]}"
        + '\n该步做完马上调用 edit_todo（action="done", item_id=对应 id）勾选，再继续第 2 步；'
        + '中途不确定还剩什么，用 get_todo(status="pending") 对账。'
    )


@tool
def get_todo(runtime: ToolRuntime, task: str = "", status: str = "all") -> str:
    """查看复杂任务的拆解清单与执行进度（todo）。

    参数说明：
    - task: 任务名。**留空则列出本会话所有任务清单及其进度**（用于确认有哪些任务、
      任务名该怎么写）；指定任务名时返回该任务的详细清单（每条的 id、完成状态与内容）。
    - status: 指定 task 时的过滤：
      - "all": 全部条目（默认）
      - "pending": 只看未完成（推进任务时最常用：先看还剩哪几步）
      - "done": 只看已完成

    触发场景（都与上面的执行循环配套）：
    - 推进途中对账："还剩哪几步没做"（status="pending"，看完再决定下一步动作）
    - 每轮开工、或上下文被压缩过之后，先对一次账，避免漏步骤或重复做
    - 勾选 / 改内容 / 删除之前，先取到子任务的条目 id
    - **回复主人之前做收尾对账**：status="pending" 要么为空，要么你已在回复里说明"还剩哪几条、卡在哪"，不能把清单丢在半路
    - 主人问"做到哪了 / 进度怎么样"时，据此汇总汇报

    返回清单内容或任务清单列表；没有清单时返回提示。
    """
    status = (status or "all").strip().lower()
    status = {
        "active": "pending", "todo": "pending", "未完成": "pending",
        "已完成": "done", "全部": "all", "complete": "done",
    }.get(status, status)
    if status not in ("all", "pending", "done"):
        return f"错误：status 仅支持 all/pending/done，收到：{status}"

    session_key = _todo_session_key(runtime)

    # 不传 task：列出本会话全部任务清单与进度
    if not (task or "").strip():
        files = _list_session_todo_files(session_key)
        if not files:
            return "当前会话还没有任何任务清单（复杂任务可用 create_todo 拆解）。"
        lines = ["本会话的任务清单："]
        for path in files:
            meta, entries, _raw = _read_todo(path)
            lines.append(
                f"- {meta.get('task') or os.path.basename(path)}"
                f"（{_todo_summary(entries)}，task_key={meta.get('task_key') or ''}）"
            )
        lines.append("要看某一份的详细清单，请再带 task 参数调用一次。")
        return "\n".join(lines)

    path = _find_todo_file(session_key, task)
    if path is None:
        return f"错误：本会话找不到任务「{task}」的清单。{_todo_task_choices(session_key)}"

    with _TODO_LOCK:
        meta, entries, raw = _read_todo(path)
        items = _todo_items(entries)
        title_task = meta.get("task") or task
        if status == "all":
            if not items:
                return f"任务「{title_task}」的清单还没有子任务（{_todo_summary(entries)}）。"
            return raw.strip()

        want_done = status == "done"
        picked = [e for e in items if e["done"] == want_done]
        label = "未完成" if status == "pending" else "已完成"
        title = f"# 任务「{title_task}」（{label}）"
        if not picked:
            return f"{title}\n\n（没有{label}的子任务；{_todo_summary(entries)}）"
        body = "\n".join(_render_todo_entry(e) for e in picked)
        return f"{title}\n\n{body}\n\n（{_todo_summary(entries)}）"


@tool
def edit_todo(
    runtime: ToolRuntime,
    task: str,
    action: str,
    item_id: str = "",
    content: str | None = None,
) -> str:
    """更新某个复杂任务的子任务状态（todo）：勾选完成 / 追加 / 改内容 / 删除。

    参数说明：
    - task: 任务名（与 create_todo 时一致；也可传清单里的 task_key）。
    - action: 动作，取值：
      - "done": 勾选完成（写为 - [x]）——**每完成一步就立刻调用一次**，别等全部做完再补记
      - "undone": 取消完成，回到未完成
      - "add": 追加子任务（content 必填，可多行，每行一条），加在清单末尾
      - "update": 改写某条子任务的内容（item_id + content）
      - "delete": 删除某条子任务（计划变更、某步不再需要时用）
    - item_id: 子任务 id（形如 t-1a2b3c，取自 create_todo / get_todo 的结果）；
      done/undone/delete 支持一次传多个 id，用逗号或空格分隔。
    - content: action="add" 时要追加的子任务内容（多行则逐行新增）；
      action="update" 时的新内容。

    触发场景：某一条子任务做完就**立刻** done（这一步不能省，不勾选等于没跟踪，主人也看不到进度）；
    执行中发现计划要调整用 add/update；某步不用做了用 delete。

    返回操作结果与最新进度；任务名/id 不存在时返回错误并列出可用项，便于修正后重试。
    """
    action = (action or "").strip().lower()
    action = {
        "complete": "done", "finish": "done", "完成": "done",
        "undone": "undone", "undo": "undone", "取消完成": "undone", "未完成": "undone",
        "add": "add", "append": "add", "追加": "add", "新增": "add",
        "update": "update", "edit": "update", "改": "update", "编辑": "update", "修改": "update",
        "delete": "delete", "remove": "delete", "删除": "delete",
    }.get(action, action)
    if action not in ("done", "undone", "add", "update", "delete"):
        return f"错误：action 仅支持 done/undone/add/update/delete，收到：{action}"

    session_key = _todo_session_key(runtime)
    path = _find_todo_file(session_key, task)
    if path is None:
        return f"错误：本会话找不到任务「{task}」的清单。{_todo_task_choices(session_key)}"

    with _TODO_LOCK:
        meta, entries, _raw = _read_todo(path)
        items = _todo_items(entries)
        title_task = meta.get("task") or task

        # ---------- 追加子任务 ----------
        if action == "add":
            texts = [" ".join(line.split()) for line in str(content or "").splitlines()]
            texts = [t for t in texts if t]
            if not texts:
                return '错误：action="add" 需要 content（要追加的子任务，多行则逐行新增）。'
            if len(items) + len(texts) > MAX_TODO_BATCH:
                return (
                    f"错误：单个清单最多 {MAX_TODO_BATCH} 条，当前已有 {len(items)} 条，"
                    f"无法再追加 {len(texts)} 条。"
                )
            for text in texts:
                if len(text) > MAX_TODO_CONTENT:
                    return f"错误：子任务过长（{len(text)} 字符，上限 {MAX_TODO_CONTENT}）：{text[:40]}…"
            used = {e["id"] for e in items}
            added = []
            for text in texts:
                tid = _new_todo_id(used)
                used.add(tid)
                entries.append({"type": "item", "id": tid, "done": False, "content": text})
                added.append(f"- {tid} {text}")
            err = _save_todo_file(path, entries, meta)
            if err:
                return err
            return (
                f"已为任务「{title_task}」追加 {len(added)} 步：\n"
                + "\n".join(added)
                + f"\n（{_todo_summary(entries)}）"
            )

        if not items:
            return (
                f'任务「{title_task}」的清单还没有子任务'
                '（可用 action="add" 追加，或 create_todo 重新拆解）。'
            )

        # ---------- 改子任务内容 ----------
        if action == "update":
            new_content = " ".join(str(content or "").split())
            if not new_content:
                return '错误：action="update" 需要 content（新的子任务内容）。'
            if len(new_content) > MAX_TODO_CONTENT:
                return (
                    f"错误：内容过长（{len(new_content)} 字符，上限 {MAX_TODO_CONTENT}）："
                    f"{new_content[:40]}…"
                )
            ids = [x for x in re.split(r"[,\s，、;；]+", item_id or "") if x]
            if len(ids) != 1:
                return "错误：action=update 一次只能指定一个 item_id。"
            target = next((e for e in items if e["id"] == ids[0]), None)
            if target is None:
                return f"错误：未找到 id 为 {ids[0]} 的子任务。{_todo_id_hint(items)}"
            if new_content == target["content"]:
                return f"子任务 {target['id']} 的内容未变化。"
            old = target["content"]
            target["content"] = new_content
            err = _save_todo_file(path, entries, meta)
            if err:
                return err
            return f"已更新子任务 {target['id']}：{old} → {new_content}\n（{_todo_summary(entries)}）"

        # ---------- 完成 / 取消完成 / 删除（支持批量） ----------
        ids = [x for x in re.split(r"[,\s，、;；]+", item_id or "") if x]
        if not ids:
            return f"错误：缺少 item_id。{_todo_id_hint(items)}"
        if len(ids) > MAX_TODO_BATCH:
            return f"错误：单次最多处理 {MAX_TODO_BATCH} 条，收到 {len(ids)} 条。"

        found: list[dict] = []
        missing: list[str] = []
        for tid in ids:
            target = next((e for e in items if e["id"] == tid), None)
            if target is None:
                missing.append(tid)
            else:
                found.append(target)
        if not found:
            return f"错误：未找到这些子任务：{', '.join(missing)}。{_todo_id_hint(items)}"

        if action == "delete":
            drop = {e["id"] for e in found}
            entries = [
                e for e in entries if not (e["type"] == "item" and e["id"] in drop)
            ]
        else:
            want_done = action == "done"
            for e in found:
                e["done"] = want_done

        err = _save_todo_file(path, entries, meta)
        if err:
            return err
        verb = {"done": "已勾选完成", "undone": "已取消完成", "delete": "已删除"}[action]
        lines = [f"{verb} {len(found)} 步："]
        lines += [f"- {e['id']} {e['content']}" for e in found]
        if missing:
            lines.append(f"（未找到：{', '.join(missing)}）")
        lines.append(f"（{_todo_summary(entries)}）")
        if action == "done":
            remaining = [e for e in _todo_items(entries) if not e["done"]]
            if remaining:
                lines.append(f"下一步：{remaining[0]['id']} {remaining[0]['content']}")
            else:
                lines.append("全部子任务已完成，请向主人汇报最终结果与产出位置。")
        return "\n".join(lines)


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