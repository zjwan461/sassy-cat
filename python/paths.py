# -*- coding: utf-8 -*-
"""
用户数据目录解析与旧数据搬迁。

背景：runtime/ 是 agent 的 sandbox 工作目录（skills 加载、脚本执行），
会话元数据与 checkpoint 属于用户数据，放那里有被模型工具篡改的风险，
统一迁移到 Electron userData（app.getPath('userData')）。

优先级：init(data_dir) 显式设置 -> 环境变量 SASSY_CAT_DATA_DIR -> 跨平台兜底
（Windows %APPDATA%\\sassy-cat；macOS ~/Library/Application Support/sassy-cat；
Linux ~/.local/share/sassy-cat），不 hardcode 用户名。
"""

import logging
import os
import shutil
import sys
import threading

logger = logging.getLogger(__name__)

APP_DIR_NAME = "sassy-cat"

_lock = threading.Lock()
_data_dir: str | None = None


def _fallback_dir() -> str:
    if sys.platform == "win32":
        base = os.getenv("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
        return os.path.join(base, APP_DIR_NAME)
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Application Support", APP_DIR_NAME)
    base = os.getenv("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, APP_DIR_NAME)


def init(data_dir: str | None = None) -> str:
    """设置数据目录（main.py 解析 --data-dir 后调用），并执行旧数据搬迁。幂等。"""
    global _data_dir
    with _lock:
        if _data_dir:
            return _data_dir
        resolved = data_dir or os.getenv("SASSY_CAT_DATA_DIR") or _fallback_dir()
        os.makedirs(resolved, exist_ok=True)
        _data_dir = resolved
        logger.info(f"用户数据目录: {resolved}")
        _migrate_legacy_db(resolved)
        return resolved


def data_dir() -> str:
    """获取数据目录；未显式 init 时惰性走兜底路径（CLI 调试场景）。"""
    global _data_dir
    if _data_dir is None:
        return init()
    return _data_dir


def data_path(name: str) -> str:
    """数据目录下某个文件的绝对路径。"""
    return os.path.join(data_dir(), name)


def _migrate_legacy_db(target_dir: str) -> None:
    """把 runtime/ 下遗留的 checkpoints.sqlite（含 -wal/-shm 伴生文件）搬迁到数据目录。

    仅当目标不存在且源存在时移动；sqlite 处于 WAL 模式时进程未启动、无并发风险。
    搬迁失败不致命：记 warning，服务照常以新空库启动（旧会话历史保留在 runtime 可手工找回）。
    """
    legacy_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "runtime")
    legacy_db = os.path.normpath(os.path.join(legacy_dir, "checkpoints.sqlite"))
    target_db = os.path.join(target_dir, "checkpoints.sqlite")
    if not os.path.isfile(legacy_db) or os.path.exists(target_db):
        return
    try:
        for suffix in ("", "-wal", "-shm"):
            src = legacy_db + suffix
            if os.path.isfile(src):
                shutil.move(src, target_db + suffix)
        logger.info(f"已将旧 checkpoints.sqlite 从 runtime/ 搬迁到 {target_dir}")
    except OSError as e:
        logger.warning(f"搬迁旧 checkpoints.sqlite 失败（将以新库启动，旧历史留在 runtime/）: {e}")
