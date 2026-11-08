# -*- coding: utf-8 -*-
"""平台化 shell 后端：Windows 用 PowerShell，macOS / Linux 用 sh。

替代原先的 `VirtualShellBackend`。设计目标（对齐 DSH / DeepSeek Harness 的 pwsh 工具语义）：

- **一条真实路径**：不再有「虚拟路径 / 真实路径」两套口径。工作区根目录就是
  `root_dir`（`runtime/`），文件工具与 shell 用同一套路径；相对路径基于工作区根目录。
- **平台原生方言**：Windows 交给 `pwsh`（7+，若已安装）或系统自带的 `powershell.exe`（5.1）；
  macOS / Linux 交给 `/bin/sh -lc`。单次调用一个全新进程，不保留跨命令状态。
- **可预期的失败**：超时按整棵进程树清理，返回 `[timed out after Ns]`；
  非零退出码以 `[exit code: N]` 附在输出末尾，而不是抛异常。
- **输出可读**：统一 UTF-8（Windows 中文环境不再 GBK 乱码），stderr 单独成段，超长截断。

文件读写、ls / glob / grep 等仍由 `LocalShellBackend`（FilesystemBackend）提供，
本模块只替换 `execute()` 的执行管线。
"""

from __future__ import annotations

import locale
import logging
import os
import shutil
import signal
import subprocess
import sys
import tempfile
from functools import lru_cache
from pathlib import Path

from deepagents.backends import LocalShellBackend
from deepagents.backends.protocol import ExecuteResponse

from agent.deepagents_path_compat import install as install_path_compat

logger = logging.getLogger(__name__)

_IS_WINDOWS = os.name == "nt"

# PowerShell 启动参数：无 logo、不加载用户 profile、非交互（不会等待 stdin）

# Windows 专用：每轮命令前置的运行时设置。
# - 输出编码固定 UTF-8：PowerShell 5.1 在中文 Windows 上默认按 GBK 输出，
#   模型/前端会看到乱码；这里在执行前把控制台与管道输出都切到 UTF-8。
# - 关掉进度条：curl / Invoke-WebRequest 之类的进度流会污染 stderr。
_PS_PROLOGUE = (
    "$ProgressPreference='SilentlyContinue';"
    "$ErrorActionPreference='Continue';"
    "try{[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)}catch{};"
    "try{$OutputEncoding=[Console]::OutputEncoding}catch{};"
)

# PowerShell 的进程退出码默认只看「脚本是否抛终止错误」，原生程序返回非 0
# （python / git / ffmpeg…）不会自动透传。这里显式把最后一个原生退出码带出去，
# 让模型看到 [exit code: N] 而不是假的 0。
_PS_EPILOGUE = "if ($null -ne $LASTEXITCODE) { exit $LASTEXITCODE }"


@lru_cache(maxsize=1)
def resolve_powershell() -> str:
    """定位 PowerShell 可执行文件：优先 pwsh（7+），回退系统自带 powershell.exe。"""
    for name in ("pwsh", "pwsh.exe", "powershell", "powershell.exe"):
        found = shutil.which(name)
        if found:
            return found
    # 兜底：Windows 系统固定路径（PATH 被裁剪时仍能用）
    return os.path.join(
        os.environ.get("SystemRoot", r"C:\Windows"),
        "System32",
        "WindowsPowerShell",
        "v1.0",
        "powershell.exe",
    )


def _decode_output(data: bytes | None) -> str:
    """把命令输出解码成文本。

    正常情况下 PowerShell 已强制 UTF-8；这里仍按候选编码兜底，
    避免旧版 Windows / 第三方原生程序把 GBK 字节直接写进管道时整段乱码。
    """
    if not data:
        return ""
    candidates = ["utf-8"]
    preferred = locale.getpreferredencoding(False)
    if preferred:
        candidates.append(preferred)
    candidates.extend(["gb18030", "latin-1"])
    for enc in candidates:
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def _kill_process_tree(proc: subprocess.Popen) -> None:
    """终止命令及其子进程。

    Windows 下 PowerShell 常会再拉起原生程序（python/node/ffmpeg…），
    只杀直接子进程会留下孤儿继续占端口；taskkill /T 按进程树清理。
    """
    try:
        if _IS_WINDOWS:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                check=False,
                timeout=10,
            )
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:  # noqa: BLE001
        pass
    try:
        proc.kill()
    except Exception:  # noqa: BLE001
        pass


def _venv_bin_dir(root_dir: str) -> str | None:
    """定位项目虚拟环境的可执行目录，用于把 python / pip 固定到项目解释器。"""
    project_root = os.path.dirname(os.path.abspath(root_dir))
    candidates = (
        os.path.join(project_root, ".venv", "Scripts"),
        os.path.join(project_root, ".venv", "bin"),
        os.path.join(project_root, "python_env"),
        os.path.join(project_root, "python_env", "bin"),
    )
    for candidate in candidates:
        if os.path.isdir(candidate):
            return candidate
    return None


class _LocalProcessBackend(LocalShellBackend):
    """公共管线：临时文件接输出 + 超时杀进程树 + 统一输出整形。

    子类只负责把平台原生的 argv 拼出来。
    """

    def __init__(
        self,
        root_dir: str | os.PathLike[str] | None = None,
        *,
        timeout: int = 120,
        max_output_bytes: int = 100_000,
        env: dict[str, str] | None = None,
        inherit_env: bool = True,
    ) -> None:
        # 先装 Windows 路径兼容层：把 deepagents 内置文件工具的 validate_path 换成
        # 「真实路径」语义（盘符路径放行、/ 开头按工作区根目录），见
        # agent/deepagents_path_compat.py 的模块说明。幂等，重复构造 backend 无副作用。
        install_path_compat()
        # 真实路径模式：相对路径基于 root_dir，绝对路径按原样使用。
        super().__init__(
            root_dir=root_dir,
            virtual_mode=False,
            timeout=timeout,
            max_output_bytes=max_output_bytes,
            env=env,
            inherit_env=inherit_env,
        )
        # 在继承环境的基础上做两项固定：
        # 1) 把项目 venv 放到 PATH 最前，`python` / `pip` 自然指向项目环境
        #    （旧实现靠正则把命令里的 python 替换成绝对路径，脆弱且只认命令位置）
        # 2) Python 子进程统一 UTF-8，避免 print 中文时按 GBK 编码报错
        env_map = dict(self._env or {})
        venv_bin = _venv_bin_dir(str(self.cwd))
        if venv_bin:
            env_map["PATH"] = venv_bin + os.pathsep + env_map.get(
                "PATH", os.environ.get("PATH", "")
            )
        env_map.setdefault("PYTHONUTF8", "1")
        env_map.setdefault("PYTHONIOENCODING", "utf-8")
        self._env = env_map

    def _resolve_path(self, key: str) -> Path:
        """把「无盘符的 /x」按工作区根目录解析（Windows）。

        deepagents 默认实现是 `Path(key)` 后判断 `is_absolute()`：Windows 上
        `/skills/a.md` 有 root 而无 drive，`is_absolute()` 为 False，拼到 cwd 上会
        替换掉整段路径 → `E:\\skills\\a.md`（盘符根），既跑出工作区，又与
        validate_path 的返回口径不一致。

        这里统一成真实文件语义：盘符 / UNC 绝对路径原样交给父类（保留 symlink 环检测），
        其余（相对路径、/ 开头、空串）一律相对工作区根目录。
        兼容层的 validate_path 已把 `/x` 换成 `x`，此处是兜底：deepagents 内部有些写入
        （如大工具结果外迁到 `/large_tool_results/...`）不经过 validate_path，直接调
        backend.write，必须在这里也纠正，否则会写到盘符根目录。
        """
        if os.name == "nt" and not Path(key).is_absolute():
            return super()._resolve_path(key.lstrip("/\\"))
        return super()._resolve_path(key)

    # ---- 子类只需实现这两个钩子 ----
    def _build_argv(self, command: str) -> list[str]:
        raise NotImplementedError

    def _clean_output(self, text: str) -> str:
        """清理平台启动噪声（默认无操作，PowerShell 会覆盖）。"""
        return text

    def _cleanup(self) -> None:
        """清理一次调用产生的临时资源（默认无操作）。"""
        return None

    def _kill_on_timeout(self) -> None:
        if self._proc is not None:
            _kill_process_tree(self._proc)

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

        argv = self._build_argv(command)
        self._proc = None
        try:
            with tempfile.TemporaryFile() as out_f, tempfile.TemporaryFile() as err_f:
                proc = subprocess.Popen(  # noqa: S603
                    argv,
                    cwd=str(self.cwd),
                    stdin=subprocess.DEVNULL,
                    stdout=out_f,
                    stderr=err_f,
                    env=self._env or None,
                    start_new_session=(not _IS_WINDOWS),
                    creationflags=(
                        subprocess.CREATE_NEW_PROCESS_GROUP if _IS_WINDOWS else 0
                    ),
                )
                self._proc = proc
                timed_out = False
                try:
                    returncode = proc.wait(timeout=effective_timeout)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    self._kill_on_timeout()
                    try:
                        returncode = proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        returncode = 124
                out_f.seek(0)
                raw_stdout = out_f.read()
                err_f.seek(0)
                raw_stderr = err_f.read()
        except Exception as e:  # noqa: BLE001
            logger.exception("shell 执行失败: %s", command[:200])
            return ExecuteResponse(
                output=f"Error executing command ({type(e).__name__}): {e}",
                exit_code=1,
                truncated=False,
            )
        finally:
            self._proc = None
            self._cleanup()

        stdout = _decode_output(raw_stdout).replace("\r\n", "\n")
        stderr = _decode_output(raw_stderr).replace("\r\n", "\n")
        stdout = self._clean_output(stdout)
        stderr = self._clean_output(stderr)

        # ---- 超时：返回 124，并尽量回带已产出的部分输出 ----
        if timed_out:
            msg = f"[timed out after {effective_timeout}s]"
            partial = "\n".join(part for part in (stdout.strip(), stderr.strip()) if part)
            if partial:
                msg = f"{msg}\n{partial}"
            return ExecuteResponse(output=msg, exit_code=124, truncated=False)

        # ---- 输出整形：stdout、[stderr] 段、退出码标记 ----
        body_parts: list[str] = []
        if stdout.strip():
            body_parts.append(stdout.rstrip("\n"))
        if stderr.strip():
            if body_parts:
                body_parts.append("[stderr]")
            body_parts.append(stderr.rstrip("\n"))
        body = "\n".join(body_parts) if body_parts else "(no output)"

        truncated = False
        limit = int(self._max_output_bytes)
        if len(body) > limit:
            body = body[:limit] + f"\n\n... Output truncated at {limit} characters."
            truncated = True

        if returncode != 0:
            body = f"{body}\n[exit code: {returncode}]"

        return ExecuteResponse(output=body, exit_code=returncode, truncated=truncated)


class PowerShellBackend(_LocalProcessBackend):
    """Windows 专用：用 PowerShell 执行命令（pwsh 优先，5.1 回退）。

    命令写入临时 .ps1（UTF-8 with BOM，PowerShell 5.1 才能正确读中文）后用
    ``-File`` 执行：避免 ``-Command`` 在报错时把整段启动脚本回显到 stderr，
    也不受 Windows 命令行长度限制。
    """

    _proc: subprocess.Popen | None = None
    _temp_path: str | None = None

    def _build_argv(self, command: str) -> list[str]:
        self._temp_path = None
        fd, path = tempfile.mkstemp(prefix="sassy-ps-", suffix=".ps1")
        with os.fdopen(fd, "w", encoding="utf-8-sig", newline="\r\n") as f:
            f.write(f"{_PS_PROLOGUE}\n{command}\n{_PS_EPILOGUE}\n")
        self._temp_path = path
        return [
            resolve_powershell(),
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            path,
        ]

    def _clean_output(self, text: str) -> str:
        """把临时脚本路径换成中性名字，避免把用户机器上的临时目录写进对话。"""
        if not text:
            return text
        if self._temp_path:
            text = text.replace(self._temp_path, "command.ps1")
            text = text.replace(self._temp_path.replace("\\", "/"), "command.ps1")
            text = text.replace(os.path.basename(self._temp_path), "command.ps1")
        return text

    def _cleanup(self) -> None:
        path = self._temp_path
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                logger.debug("清理 PowerShell 临时脚本失败: %s", path)


class PosixShellBackend(_LocalProcessBackend):
    """macOS / Linux：用 /bin/sh 执行命令。"""

    _proc: subprocess.Popen | None = None

    def _build_argv(self, command: str) -> list[str]:
        return ["/bin/sh", "-lc", command]


def create_shell_backend(
    root_dir: str | os.PathLike[str] | None = None,
    *,
    timeout: int = 120,
    max_output_bytes: int = 100_000,
    env: dict[str, str] | None = None,
    inherit_env: bool = True,
) -> LocalShellBackend:
    """按平台选择 shell 后端：Windows → PowerShell，其它 → sh。"""
    cls = PowerShellBackend if _IS_WINDOWS else PosixShellBackend
    return cls(
        root_dir=root_dir,
        timeout=timeout,
        max_output_bytes=max_output_bytes,
        env=env,
        inherit_env=inherit_env,
    )


__all__ = [
    "PowerShellBackend",
    "PosixShellBackend",
    "create_shell_backend",
    "resolve_powershell",
]
