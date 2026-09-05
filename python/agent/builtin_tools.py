from langchain.tools import tool
from datetime import datetime

from typing import Literal
from tavily import TavilyClient
import os
import sys
import subprocess
from pathlib import Path


@tool(description="获取当前时间日期")
def get_date_time():
    now = datetime.now()
    # 输出示例：2026-08-21 15:30:22.123456
    # 转字符串格式化
    return now.strftime("%Y-%m-%d %H:%M:%S")


tavily_api_key = os.getenv("TAVILY_API_KEY")
tavily_client = TavilyClient(api_key=tavily_api_key)


@tool
def internet_search(
    query: str,
    max_results: int = 5,
    topic: Literal["general", "news", "finance"] = "general",
    include_raw_content: bool = False,
):
    """运行网络搜索"""
    return tavily_client.search(
        query,
        max_results=max_results,
        include_raw_content=include_raw_content,
        topic=topic,
    )


# 项目根目录（builtin_tools.py 位于 python/agent/ 下，向上两级）
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 候选 Python 解释器路径，按优先级排列：.venv 在前，python_env 在后
PYTHON_CANDIDATES = [
    PROJECT_ROOT / ".venv" / "Scripts" / "python.exe",  # Windows 虚拟环境
    PROJECT_ROOT / ".venv" / "bin" / "python",          # POSIX 虚拟环境
    PROJECT_ROOT / "python_env" / "python.exe",         # Windows 嵌入式 Python
    PROJECT_ROOT / "python_env" / "bin" / "python",     # POSIX 嵌入式 Python
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

    output = [f"解释器：{python_exe}", f"退出码：{result.returncode}"]
    if result.stdout:
        output.append(f"标准输出：\n{result.stdout}")
    if result.stderr:
        output.append(f"错误输出：\n{result.stderr}")
    if not result.stdout and not result.stderr:
        output.append("（无任何输出）")
    return "\n".join(output)


@tool
def run_command(command: str):
    """执行系统命令，返回执行结果。"""
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            cwd=str(PROJECT_ROOT),
        )
    except subprocess.TimeoutExpired:
        return f"执行超时（超过 60 秒），命令：{command}"
    except Exception as e:
        return f"执行失败：{e}，命令：{command}"

    output = [f"退出码：{result.returncode}"]
    if result.stdout:
        output.append(f"标准输出：\n{result.stdout}")
    if result.stderr:
        output.append(f"错误输出：\n{result.stderr}")
    if not result.stdout and not result.stderr:
        output.append("（无任何输出）")
    return "\n".join(output)