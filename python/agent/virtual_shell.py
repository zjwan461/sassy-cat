# -*- coding: utf-8 -*-
"""VirtualShellBackend：LocalShellBackend 入口 + run_command 执行管线。

设计目标（对比分析后的合流方案）：
- 对框架保持 LocalShellBackend 身份：工具名仍是 execute，
  SkillsMiddleware 提示词、interrupt_on 审批键名、超时/截断语义全部无缝。
- 对底层复用项目里 run_command（builtin_tools）沉淀的 Windows 加固逻辑：
  1. 虚拟路径重写：/xxx/... → WORK_DIR 下真实路径（virtual_mode 语义对齐）
  2. 解释器钉死：命令名位置的 python/pip → 项目 .venv 解释器绝对路径
  3. cmd 假成功拦截：cmd 缺 /c（或误用 /k）直接拒绝并给出正确写法
  4. start 标题陷阱：start 后紧跟路径/带引号参数时自动补空标题 ""
  5. GBK 乱码治理：字节捕获后按 OEM 代码页多候选解码（_decode_output）

与 run_command 的差异：
- run_command 收 argv 数组（无 shell 组合能力）；本类收 shell 命令字符串，
  保留管道/重定向/&& 链。因此加固逻辑以"字符串级"实现：
  虚拟路径用正则重写，python/cmd/start 在"命令位置"（字符串开头、
  分隔符 & ; | && || 之后、cmd /c 之后）做识别与替换。
- 执行方式与 shell=True 内部行为一致（CreateProcess 原始命令行
  `cmd.exe /c <字符串>`，不经 list2cmdline 转义，避免引号地狱）。
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from typing import TYPE_CHECKING

from deepagents.backends import LocalShellBackend
from deepagents.backends.protocol import ExecuteResponse

from agent.tools.builtin_tools import (
    _comspec,
    _decode_output,
    _find_python,
    _looks_like_switch,
    _needs_start_title,
)

if TYPE_CHECKING:
    pass

_IS_WINDOWS = os.name == "nt"

# 候选虚拟路径：/ 前面不能是 字母/数字/下划线/冒号/点/斜杠/反斜杠/连字符，
# 借此排除 URL（x.com/p）、盘符（D:/p）、相对路径（./p ../p）、开关值（-x/p）等；
# 捕获组1 = 第一段目录名，捕获组2 = 其余路径段（可能为空，为空即单段）
_VPATH_RE = re.compile(r"(?<![\w:/\\.\-])/([\w.\-]+)((?:/[\w.\-+@%~]+)*)")

# 重定向目标（> / >> / < 后紧跟的 /xxx）：该位置的 token 绝不可能是 cmd 开关
# （开关不会出现在重定向右侧），即使文件尚不存在也应无条件重写为 WORK_DIR 路径，
# 否则 cmd 会把 "/name" 当非法设备/路径报"命令语法不正确"。
# 捕获组1 = 重定向符，捕获组2 = 第一段，捕获组3 = 其余段
_REDIR_RE = re.compile(r"([<>]{1,2})\s*((?<![\w:/\\.\-])/([\w.\-]+)((?:/[\w.\-+@%~]+)*))")

# 命令位置上的关键 token：字符串开头、分隔符（& ; | ，覆盖 && ||）之后、
# 或 cmd /c、cmd /k 之后。token 后不能紧跟 单词字符/点/连字符，
# 避免把 D:\py\python.exe 里的 python、或 python3.11 之类误判。
_CMD_POS_RE = re.compile(
    r"(?:(?:^|(?<=[&;|]))\s*|(?<=/c\s)|(?<=/k\s))"
    r"(python3?|pip3?|cmd(?:\.exe)?|start)(?![\w.\-])",
    re.IGNORECASE,
)

# 取某位置之后的下一个 token（带引号参数或裸参数）
_NEXT_TOKEN_RE = re.compile(r'\s+("[^"]*"|\'[^\']*\'|\S+)')


def _q(path: str) -> str:
    """Windows 路径含空格时加双引号（POSIX 一般不需要，统一加也无害）。"""
    if _IS_WINDOWS:
        return f'"{path}"'
    return path


class VirtualShellBackend(LocalShellBackend):
    """LocalShellBackend 外观，execute() 底层走 run_command 同款加固管线。"""

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        if not command or not isinstance(command, str):
            return ExecuteResponse(
                output="Error: Command must be a non-empty string.",
                exit_code=1,
                truncated=False,
            )
        effective_timeout = timeout if timeout is not None else self._default_timeout
        if effective_timeout <= 0:
            raise ValueError(f"timeout must be positive, got {effective_timeout}")

        # ---- 管线 1：虚拟路径重写（/xxx → WORK_DIR/xxx） ----
        cmd = self._rewrite_virtual_paths(command)

        # ---- 管线 2：命令位置加固（python 钉死 / cmd /c 校验 / start 补标题） ----
        cmd, problem = self._harden_command_positions(cmd)
        if problem:
            return ExecuteResponse(output=problem, exit_code=1, truncated=False)

        # ---- 执行：字节捕获（解码交给 _decode_output，避免 GBK 乱码） ----
        try:
            if _IS_WINDOWS:
                # 与 Python shell=True 内部行为一致：cmd.exe /c "<命令>" 整体再包一层引号。
                # 这层引号解决 cmd 的引号剥离规则：若命令以带引号路径开头
                # （如 python 被钉死为 "D:\...\.venv\Scripts\python.exe"），
                # 裸命令行 ""D:\py.exe" -c "x"" 会被 cmd 剥掉首尾引号而破碎；
                # 外层多包一对引号后，cmd 剥掉的正是外层这一对，内部结构原样保留。
                argv: list[str] | str = f'{_comspec()} /c "{cmd}"'
                shell = False
            else:
                argv = cmd
                shell = True
            result = subprocess.run(  # noqa: S603
                argv,
                shell=shell,
                check=False,
                capture_output=True,
                stdin=subprocess.DEVNULL,
                timeout=effective_timeout,
                env=(self._env if self._env else None),
                cwd=str(self.cwd),
                start_new_session=(sys.platform != "win32"),
            )
        except subprocess.TimeoutExpired:
            if timeout is not None:
                msg = (
                    f"Error: Command timed out after {effective_timeout} seconds "
                    "(custom timeout). The command may be stuck or require more time."
                )
            else:
                msg = (
                    f"Error: Command timed out after {effective_timeout} seconds. "
                    "For long-running commands, re-run using the timeout parameter."
                )
            return ExecuteResponse(output=msg, exit_code=124, truncated=False)
        except Exception as e:  # noqa: BLE001
            return ExecuteResponse(
                output=f"Error executing command ({type(e).__name__}): {e}",
                exit_code=1,
                truncated=False,
            )

        # ---- 输出整形：与 LocalShellBackend 的 ExecuteResponse 语义一致 ----
        stdout = _decode_output(result.stdout)
        stderr = _decode_output(result.stderr)
        output_parts = []
        if stdout:
            output_parts.append(stdout)
        if stderr:
            stderr_lines = stderr.strip().split("\n")
            output_parts.extend(f"[stderr] {line}" for line in stderr_lines)
        output = "\n".join(output_parts) if output_parts else "<no output>"

        truncated = False
        if len(output) > self._max_output_bytes:
            output = output[: self._max_output_bytes]
            output += f"\n\n... Output truncated at {self._max_output_bytes} bytes."
            truncated = True

        if result.returncode != 0:
            output = f"{output.rstrip()}\n\nExit code: {result.returncode}"

        return ExecuteResponse(
            output=output,
            exit_code=result.returncode,
            truncated=truncated,
        )

    # ------------------------------------------------------------------
    # 管线 1：虚拟路径重写
    # ------------------------------------------------------------------
    def _rewrite_virtual_paths(self, cmd: str) -> str:
        """把 /xxx/... 虚拟路径重写为 WORK_DIR 下的真实绝对路径。"""
        root = str(self.cwd)
        # 本条命令内被重定向创建的文件（如 echo x > /a.txt && type /a.txt）：
        # 后续再引用同一虚拟路径时，虽然磁盘上还不存在（sub 单遍、执行更在后），
        # 但语义上必然指向 WORK_DIR，直接重写，不再走存在性安全阀。
        created: set[str] = set()

        def redir_repl(m: re.Match[str]) -> str:
            # 重定向目标：无条件重写（新建文件场景），不做存在性检查
            first, tail = m.group(3), m.group(4)
            created.add(first + tail.lower())
            real = os.path.join(root, first)
            if _IS_WINDOWS:
                return f"{m.group(1)} {(real + tail).replace('/', chr(92))}"
            return f"{m.group(1)} {real + tail}"

        cmd = _REDIR_RE.sub(redir_repl, cmd)

        def repl(m: re.Match[str]) -> str:
            first, rest = m.group(1), m.group(2)
            real = os.path.join(root, first)
            # 多段路径（/a/b）：Windows 下 cmd 开关不可能是多段，无条件重写，
            # 覆盖"目标目录尚不存在"的新建场景；POSIX 保留存在性检查，
            # 避免把 /tmp/x、/usr/bin/y 等真实系统路径错误映射进 WORK_DIR。
            if not (rest and _IS_WINDOWS):
                # 安全阀：第一段在 WORK_DIR 下不存在、且不是本命令刚创建的
                # 重定向目标时，原样保留（cmd 开关 /c /b /s 等不受影响）
                if (first + rest.lower()) not in created and not os.path.exists(real):
                    return m.group(0)
            if _IS_WINDOWS:
                return (real + rest).replace("/", "\\")
            return real + rest

        return _VPATH_RE.sub(repl, cmd)

    # ------------------------------------------------------------------
    # 管线 2：命令位置加固
    # ------------------------------------------------------------------
    def _harden_command_positions(self, cmd: str) -> tuple[str, str | None]:
        """在命令位置做三类加固，返回 (新命令, 拒绝原因或 None)。

        - python/python3/pip/pip3 → 替换为项目解释器绝对路径
          （pip 展开为 "<python>" -m pip）
        - cmd → 后随 token 必须是 /c；/k 或缺失/其它一律拒绝（假成功陷阱）
        - start → 后随路径/带引号参数时自动补空标题 ""（标题吞噬陷阱）
        """
        matches = list(_CMD_POS_RE.finditer(cmd))
        if not matches:
            return cmd, None

        out = cmd
        # 从后往前替换，避免前面的替换使后面的 span 失效
        for m in reversed(matches):
            token = m.group(1).lower()
            start, end = m.span(1)
            nxt = _NEXT_TOKEN_RE.match(out, end)
            nxt_tok = nxt.group(1) if nxt else None

            if token.startswith("cmd"):
                nxt_norm = (nxt_tok or "").strip("\"'").lower()
                if nxt_norm == "/k":
                    return cmd, (
                        "命令未执行：本工具是非交互环境，cmd /k 会保留 shell 并等待输入，"
                        '拿不到结果。请改用 /c（执行后退出），例如 "cmd /c dir"。'
                    )
                if nxt_norm != "/c":
                    return cmd, (
                        "命令未执行：Windows 下调用 cmd 必须紧跟 /c（执行后退出）开关。"
                        "缺少 /c 时 cmd 进入交互式 shell：打印版本横幅后立即退出，"
                        "退出码 0 但命令从未执行。"
                        '正确写法示例：cmd /c dir、cmd /c start "" /code/index.html。'
                    )
            elif token in ("python", "python3"):
                out = out[:start] + _q(_find_python()) + out[end:]
            elif token in ("pip", "pip3"):
                out = out[:start] + _q(_find_python()) + " -m pip" + out[end:]
            elif token == "start":
                if (
                    nxt_tok
                    and not _looks_like_switch(nxt_tok.strip("\"'"))
                    and _needs_start_title(nxt_tok)
                ):
                    out = out[:end] + ' ""' + out[end:]

        return out, None


__all__ = ["VirtualShellBackend"]
