# -*- coding: utf-8 -*-
"""deepagents 文件工具的 Windows 路径兼容层（方案 A：真实路径 + 垫片）。

为什么需要它
------------
deepagents 的 8 个内置文件工具（ls / read_file / write_file / edit_file / delete /
glob / grep / download）在 middleware 层都会先调 ``validate_path()``，而这个函数假定
传入的是「POSIX 虚拟路径」：

1. ``^[a-zA-Z]:`` 开头的盘符绝对路径一律抛
   ``Windows absolute paths are not supported``；
2. 相对路径会被无条件补上前导 ``/``；而 Windows 上 ``Path("/x")`` **不是**绝对路径
   （有 root 无 drive），经 backend._resolve_path 拼到 cwd 上会落到「盘符根」——
   ``skills/a.md`` 变成 ``E:\\skills\\a.md``，而不是工作区的 ``...\\runtime\\skills\\a.md``。

本项目 backend 用 ``virtual_mode=False``（见 agent/shell_backend.py），但该校验在
middleware 里、不在 backend 里，``virtual_mode`` 对它无效。后果（线上实测）：

- 技能清单由 SkillsMiddleware 渲染成**真实绝对路径**，提示词还写着 "Always use
  absolute paths from the skill list"，模型照抄进 read_file → 必然报错；
- 模型按报错提示改猜 ``/workspaces/...``，恰好因 Windows 的拼接语义
  （``E:\\a`` + ``/workspaces/x`` → ``E:\\workspaces\\x``）跑通，于是把错误写法固化下来；
- 相对路径反而始终解析到盘符根，属于尚未暴露的同类问题；
- 大工具结果外迁写入 ``/large_tool_results/...``（middleware 直接调 backend.write，
  不经过 validate_path），同样会落到盘符根。

修复思路
--------
只在 Windows 下把「路径规范化」还原成真实文件系统语义：

- 盘符 / UNC 绝对路径：``ntpath.normpath`` 规范化后**原样放行**（仍拦 ``..`` 与 ``~``）；
- 其余（含以 ``/`` 开头的）：一律视为「相对工作区根目录」；
- backend 侧同步覆写 ``_LocalProcessBackend._resolve_path``（见 shell_backend.py），
  让不经 validate_path 的内部路径（外迁目录、skills 直接调用 backend 的地方）也落在
  工作区内。

为什么是 monkeypatch
--------------------
``validate_path`` 被 ``deepagents.middleware.filesystem`` 与
``deepagents.middleware._fs_interrupt`` 在导入期各持一份引用，且 8 个工具都直接调用，
没有公开的注入点；子类化 FilesystemMiddleware 需要重写 8 个工具工厂，改动面更大。
业界同款做法（Ascend msagent 的 deepagents_compat.py）也是替换这两个模块属性。

已知代价：绑定 deepagents 私有函数。上游至 0.7.34 仍未修复，升级后若行为变化，
本模块的 ``install()`` 自检会在启动时直接报错，而不是静默退化。
"""

from __future__ import annotations

import logging
import ntpath
import os
import re

logger = logging.getLogger(__name__)

# 盘符绝对路径（C:\ / C:/）或 UNC 路径（\\server\share）
_WINDOWS_ABS_RE = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\)")

# 兼容两种分隔符的切分（Windows 上模型两种都会写）
_SEP_RE = re.compile(r"[\\/]+")

# 原始实现：模块导入时先抓一份，install() 里再按当时状态刷新（若已有第三方补丁则链到它）
try:  # pragma: no cover - 依赖 deepagents 的导入结构
    from deepagents.backends.utils import validate_path as _original_validate_path
except ImportError:  # pragma: no cover
    _original_validate_path = None

_installed = False


def _reject_traversal(path: str) -> None:
    """按路径**组件**拦截 ``..`` 与 ``~``（与 deepagents 原语义一致）。

    deepagents 原实现用 ``PurePosixPath(...).parts`` 判断，Windows 反斜杠不会被拆开，
    所以这里换成按 ``\\`` 和 ``/`` 双分隔符切分。
    """
    if path.startswith("~"):
        msg = f"Path traversal not allowed: {path}"
        raise ValueError(msg)
    if ".." in [part for part in _SEP_RE.split(path) if part]:
        msg = f"Path traversal not allowed: {path}"
        raise ValueError(msg)


def _win_validate_path(path, *, allowed_prefixes=None):
    """Windows 感知版 ``validate_path``：放行真实路径，返回「可直接交给 backend」的形式。

    - 非 Windows / 非字符串 / 显式传入 allowed_prefixes（permissions 场景，本项目未启用）
      → 完全交回原实现，保持语义不变；
    - 盘符或 UNC 绝对路径 → ``ntpath.normpath`` 规范化后返回，backend 会原样使用；
    - 其余（相对路径、以 ``/`` 开头的旧写法）→ 去掉前导分隔符，返回相对工作区根的
      POSIX 路径，交给 backend._resolve_path 拼到 root_dir 上。
    """
    if os.name != "nt" or not isinstance(path, str) or allowed_prefixes is not None:
        return _original_validate_path(path, allowed_prefixes=allowed_prefixes)

    _reject_traversal(path)

    if _WINDOWS_ABS_RE.match(path):
        return ntpath.normpath(path)

    # "skills/a.md" / "/skills/a.md" → "skills/a.md"；"/" → ""（等价于工作区根目录）
    return "/".join(part for part in _SEP_RE.split(path) if part)


def _patch_targets() -> list[tuple[object, str]]:
    """收集所有持有 validate_path 引用的 deepagents 模块。"""
    from deepagents.backends import utils as backend_utils
    from deepagents.middleware import filesystem as filesystem_middleware

    targets: list[tuple[object, str]] = [
        (backend_utils, "validate_path"),
        (filesystem_middleware, "validate_path"),
    ]
    # permissions → interrupt 的换算模块（本项目未启用 permissions，但一并覆盖，
    # 避免以后启用时因导入期引用而绕过垫片）
    try:
        from deepagents.middleware import _fs_interrupt as fs_interrupt
    except ImportError:  # pragma: no cover - 取决于 deepagents 版本
        pass
    else:
        targets.append((fs_interrupt, "validate_path"))
    return targets


def _self_check() -> None:
    """安装后自检：确认补丁真的生效，且行为符合预期。"""
    from deepagents.middleware import filesystem as filesystem_middleware

    if filesystem_middleware.validate_path is not _win_validate_path:
        msg = (
            "deepagents 路径兼容层未生效：middleware.filesystem.validate_path 仍指向 "
            f"{filesystem_middleware.validate_path!r}。多半是升级 deepagents 后导入结构变化，"
            "请复查 agent/deepagents_path_compat.py。"
        )
        raise RuntimeError(msg)

    sample = r"C:\Windows\System32\drivers\etc\hosts"
    if _win_validate_path(sample) != ntpath.normpath(sample):
        msg = f"deepagents 路径兼容层自检失败：{sample!r} 未被原样放行"
        raise RuntimeError(msg)

    # 危险路径必须仍被拒绝（防止垫片把安全边界一起放宽）
    for bad in ("../etc", "..\\Windows", "~/a", r"C:\a\..\b"):
        try:
            _win_validate_path(bad)
        except ValueError:
            continue
        msg = f"deepagents 路径兼容层自检失败：危险路径 {bad!r} 未被拒绝"
        raise RuntimeError(msg)


def install() -> None:
    """把 Windows 感知的 validate_path 装入 deepagents（幂等，可重复调用）。

    仅在 Windows 上做任何事；POSIX 上完全没有必要改动框架行为。
    """
    global _original_validate_path, _installed

    if os.name != "nt" or _installed:
        return

    # 先抓住原实现（若已有第三方补丁，则链到它而不是绕过它）
    from deepagents.backends import utils as backend_utils

    _original_validate_path = backend_utils.validate_path

    replaced = []
    for module, attr in _patch_targets():
        current = getattr(module, attr, None)
        if current is _win_validate_path:
            continue
        if current is not _original_validate_path:
            logger.warning(
                "deepagents 路径兼容层：%s.%s 已被其它实现替换（%r），仍覆盖为本项目版本",
                module.__name__,
                attr,
                current,
            )
        setattr(module, attr, _win_validate_path)
        replaced.append(f"{module.__name__}.{attr}")

    _self_check()
    _installed = True

    try:
        import deepagents

        version = getattr(deepagents, "__version__", "unknown")
    except Exception:  # noqa: BLE001 - 版本号只用于日志
        version = "unknown"
    logger.info(
        "deepagents 路径兼容层已安装（deepagents %s）：盘符/UNC 绝对路径放行，"
        "/ 开头按工作区根目录解析；已替换 %s",
        version,
        ", ".join(replaced) or "(无，已是本实现)",
    )


__all__ = ["install"]