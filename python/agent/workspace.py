# -*- coding: utf-8 -*-
"""工作区解析：把「用户选择的工作区」与「应用内部数据目录」分开。

- 工作区（workspace）：文件工具与 shell 的根目录，用户可在设置页选择任意本地目录；
  配置项 `agent.workspace` 为空时回退到应用内部的 `runtime/`。
- 应用数据目录（runtime）：技能库、todo 清单、dsh home、预览等内部资源，
  始终固定在应用目录下，不随工作区变化，避免把内部文件混进用户项目。

本模块刻意不在导入期固化路径：配置热重载（config.invalidate → agent 重建）后，
下一次 resolve_workspace() 就会读到新值。
"""

from __future__ import annotations

import logging
import os

from agent.constant import WORK_DIR

logger = logging.getLogger(__name__)


def default_workspace() -> str:
    """未选择工作区时的默认目录（应用内部 runtime）。"""
    return WORK_DIR


def resolve_workspace(cfg=None) -> str:
    """解析当前生效的工作区绝对路径。

    - 配置缺失/为空 → 默认工作区；
    - 配置了但目录不存在 → 记 warning 并回退默认（宁可直接聊天，也不要文件工具一启动就报错）；
    - 支持 `~` 与环境变量展开，返回值统一为绝对路径。
    """
    if cfg is None:
        import config_loader

        cfg = config_loader.current()

    try:
        raw = str(cfg.get("agent.workspace") or "").strip()
    except AttributeError:
        raw = ""

    if not raw:
        return default_workspace()

    path = os.path.abspath(os.path.expanduser(os.path.expandvars(raw)))
    if os.path.isdir(path):
        return path

    logger.warning("配置的工作区不存在，回退默认工作区: %s", raw)
    return default_workspace()


def is_default_workspace(workspace: str | None = None) -> bool:
    """判断给定（或当前解析出的）工作区是否就是默认目录。"""
    current = workspace or resolve_workspace()
    return os.path.normcase(os.path.abspath(current)) == os.path.normcase(
        os.path.abspath(default_workspace())
    )


__all__ = ["default_workspace", "resolve_workspace", "is_default_workspace"]
