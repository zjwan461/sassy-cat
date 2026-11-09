# -*- coding: utf-8 -*-
"""execute 工具的免确认白名单：只对「跑技能脚本」这类可预期命令跳过人工确认。

背景
----
``agent.interruptOn.execute=True`` 会对**每一条** shell 命令弹确认（截图里一次技能
调用就积了 3 条待确认），连
``python skills/weather-skill/scripts/fetch_weather.py --lat ...`` 也要点一次，交互噪音
远大于风险。这里给 HumanInTheLoopMiddleware 挂一个 ``when`` 谓词（langchain 1.3.18
的 InterruptOnConfig 支持，见 human_in_the_loop.py:195）：命中白名单 → 自动放行，
其余命令照旧打断等主人确认。

安全边界（重要）
--------------
PowerShell 是完整编程语言，白名单只能做「宁可多问一次，不可少问一次」的近似。因此
只认一种**窄形状**，任何一条不满足都返回 False（= 仍然确认）：

  1. 按 ``;``、``\\r``、``\\n`` 切成多条语句，**每一条**都必须命中下列规则之一；
  2. 允许的语句只有两类：
     - 切目录：``Set-Location`` / ``sl`` / ``cd`` / ``chdir <目录>``，目录必须已存在且在
       工作区内；
     - 跑技能脚本：``python <脚本> <参数...>``，脚本必须位于
       ``skills/<技能>/scripts/**`` 且是已存在的 ``.py``；
  3. 命令里出现反引号、``$``、``|``、``>``、``<``、``&``、括号、花括号、``*``、``?``
     等拼接/重定向/子表达式/通配字符，整条命令直接不放行；
  4. 不做任何变量展开或通配展开的推测——看到这类字符就退回人工确认。

为什么脚本限定在 skills/*/scripts
--------------------------------
工作区里的其他 .py 可能是 Agent 刚写出来的文件：write_file 有确认，但「写 + 自动执行」
两步连起来就能绕过确认。技能目录是主人安装的可信资产（提示词也禁止随意修改），
只放行它们才能既解决噪音又不引入新的提权路径。
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from agent.constant import SKILLS_DIR
from agent.workspace import resolve_workspace

logger = logging.getLogger(__name__)

# 语句分隔：PowerShell 的 ; 与换行
_STATEMENT_SPLIT_RE = re.compile(r"[;\r\n]+")

# 切目录：Set-Location / sl / cd / chdir（PowerShell 别名）
_CD_RE = re.compile(r"^(?:Set-Location|sl|cd|chdir)\s+(?P<target>\S.*)$", re.IGNORECASE)

# 跑脚本：项目 venv 的 python（不接受 -c/-m：这类写法会让「脚本」不是路径，直接不匹配）
_PY_RE = re.compile(
    r"^(?:python|python3)(?:\.exe)?\s+(?P<script>\S+)(?:\s+(?P<args>.*))?$",
    re.IGNORECASE,
)

# 任何拼接 / 重定向 / 子表达式 / 通配字符：命中即整条命令退回人工确认
_DENY_CHARS = frozenset("`$|><&(){}*?!")

# 允许的 shell 解释器（与 agent/shell_backend.py 一致：Windows PowerShell / POSIX sh）
_QUOTES = "\"'"


def _unquote(token: str) -> str:
    token = token.strip()
    if len(token) >= 2 and token[0] in _QUOTES and token[-1] == token[0]:
        return token[1:-1]
    return token


def _resolve(token: str, base: Path) -> Path | None:
    """把语句里的路径解析成绝对路径；解析失败返回 None。

    口径与文件工具保持一致：盘符 / UNC 绝对路径原样使用；无盘符的 ``/x`` 按工作区
    根目录（Windows 上 ``Path('/x')`` 会被拼到盘符根，必须显式纠正）。
    """
    token = _unquote(token)
    if not token:
        return None
    path = Path(token)
    if not path.is_absolute():
        if token[:1] in ("/", "\\"):
            path = Path(token.lstrip("/\\"))
        path = base / path
    try:
        return path.resolve()
    except (OSError, RuntimeError):
        return None


def _inside(path: Path, root: Path) -> bool:
    try:
        root = root.resolve()
    except (OSError, RuntimeError):
        return False
    return path == root or root in path.parents


def _is_skill_script(path: Path) -> bool:
    """只放行 skills/<技能>/scripts/** 下真实存在的 .py。"""
    try:
        relative = path.relative_to(Path(SKILLS_DIR).resolve())
    except (ValueError, OSError):
        return False
    parts = relative.parts
    # <技能>/scripts/<脚本>.py 或 <技能>/scripts/<子包>/<脚本>.py
    if len(parts) < 3 or parts[1] != "scripts":
        return False
    return path.suffix.lower() == ".py" and path.is_file()


def is_auto_approved(command: str) -> bool:
    """判断一条 execute 命令是否属于「免确认」白名单。

    任何解析不确定的地方都返回 False（继续人工确认）。
    """
    if not isinstance(command, str):
        return False
    command = command.strip()
    if not command:
        return False
    if any(ch in _DENY_CHARS for ch in command):
        return False

    # cwd 跟随当前工作区（设置页可切换），技能目录固定在应用数据目录下
    work_dir = Path(resolve_workspace())
    cwd = work_dir.resolve()

    segments = [segment.strip() for segment in _STATEMENT_SPLIT_RE.split(command) if segment.strip()]
    if not segments:
        return False

    for segment in segments:
        cd_match = _CD_RE.match(segment)
        if cd_match:
            target = _resolve(cd_match.group("target"), cwd)
            if target is None or not _inside(target, work_dir) or not target.is_dir():
                return False
            cwd = target
            continue

        py_match = _PY_RE.match(segment)
        if py_match:
            script = _resolve(py_match.group("script"), cwd)
            if script is None or not _is_skill_script(script):
                return False
            continue

        return False

    return True


def apply_execute_allowlist(interrupt_on: Mapping[str, Any] | None) -> dict[str, Any]:
    """把 ``interruptOn.execute`` 换成带 ``when`` 谓词的 InterruptOnConfig。

    - 未配置 / 显式 False → 原样返回（execute 不打断）；
    - True 或已有的 dict 配置 → 补上 ``when``：命中白名单时返回 False（自动放行），
      否则返回 True（继续确认）。若调用方自带 ``when``，以它为基准、本白名单只做「放宽」：
      ``external_when`` 返回 False（要求不打断）时本层不会再把它变回打断。
    """
    config = dict(interrupt_on or {})
    raw = config.get("execute")
    if raw is None or raw is False:
        return config

    merged: dict[str, Any] = dict(raw) if isinstance(raw, Mapping) else {}
    merged.setdefault("allowed_decisions", ["approve", "reject"])
    external_when = merged.get("when")

    def _when(request: Any) -> bool:
        try:
            command = (request.tool_call.get("args") or {}).get("command", "")
        except AttributeError:  # 防御：非 ToolCallRequest 结构一律按需确认处理
            return True
        wants_interrupt = True if external_when is None else bool(external_when(request))
        return wants_interrupt and not is_auto_approved(command)

    merged["when"] = _when
    config["execute"] = merged
    return config


__all__ = ["apply_execute_allowlist", "is_auto_approved"]