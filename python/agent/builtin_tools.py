from langchain.tools import tool, ToolRuntime
from datetime import datetime

from typing import Literal
from tavily import TavilyClient
import os
import sys
import subprocess
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

# 项目根目录（builtin_tools.py 位于 python/agent/ 下，向上两级）
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 工作目录（规范化为绝对路径）
work_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../..", "runtime"))

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


def _convert_virtual_path(segment: str) -> list[str]:
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
    if (
        segment.startswith("C:")
        or segment.startswith("D:")
        or segment.startswith("E:")
        or segment.startswith("F:")
        or segment.startswith("G:")
        or segment.startswith("H:")
        or segment.startswith("Z:")
    ):
        raise ValueError("Windows环境下不得使用真实盘符作为变量开头")
    
    # 使用 in 操作符正确检查成员关系
    if segment in ("python", "python3"):
        # 使用项目中实际可用的 Python 解释器绝对路径
        return [_find_python()]
    elif segment in ("pip", "pip3"):
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
def run_command(command: list[str]):
    """执行系统命令，返回执行结果。

    参数为命令片段数组，例如：["python", "/skills/test.py", "--arg", "value"]
    支持虚拟路径自动转换：数组中以 / 开头的路径片段会自动转换为真实路径。
    不得使用真实路径作为参数传入，比如D://skills, 命令行参数仅支持虚拟环境路径参数，必须是/开头。
    调用如python,pip,java,node,npm,pnpm,go ... 等等开发常用命令时，不要使用绝对路径，只能使用命令本身。如：直接用python,java等，不啊哟使用/home/user/java 这种绝对路径。
    Windows环境下不得使用真实盘符作为变量开头，比如D:/python.exe等。
    """
    try:
        # 遍历每个片段，将虚拟路径转换为真实路径（每个片段可能展开为多个）
        real_command = []
        for seg in command:
            real_command.extend(_convert_virtual_path(seg))
        # 拼接为字符串用于 shell 执行（支持 dir、echo 等 shell 内置命令）
        command_str = subprocess.list2cmdline(real_command)
        result = subprocess.run(
            command_str,
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            cwd=work_dir,
        )
    except subprocess.TimeoutExpired:
        return f"执行超时（超过 60 秒），命令：{command_str}"
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
