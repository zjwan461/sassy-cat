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