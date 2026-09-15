# -*- coding: utf-8 -*-
"""
数据库连接和会话管理。

使用 SQLAlchemy 异步引擎 + aiosqlite 驱动。
数据库文件位于用户数据目录下的 messages.sqlite。

表结构由 Alembic migration 管理（python/server/db/migrations/），
启动时自动：
  1. 旧库（无 alembic_version 表但已有业务表）→ 自动 stamp 到基线版本
     （_LEGACY_BASELINE_REVISION，即旧 create_all 时代对应的迁移），
     之后的迁移会照常 upgrade 应用
  2. alembic upgrade head（应用未应用的迁移）
  3. 执行 seed（幂等的初始化数据）
"""

import asyncio
import logging
import os
import sqlite3
import threading

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

import paths

logger = logging.getLogger(__name__)

# 数据库 URL（异步 SQLite）
_db_url: str | None = None
_engine = None
_async_session_factory = None
_lock = threading.Lock()
_initialized = False


def _get_db_path() -> str:
    """获取数据库文件路径"""
    return paths.data_path("messages.sqlite")


def _get_db_url() -> str:
    """构建数据库 URL"""
    global _db_url
    if _db_url is None:
        db_path = _get_db_path()
        _db_url = f"sqlite+aiosqlite:///{db_path}"
    return _db_url


# 已存在任意一张即视为"旧库"（由 create_all 时代建出的业务表）
_LEGACY_BUSINESS_TABLES = {
    "messages",
    "attachments",
    "knowledge_bases",
    "kb_documents",
    "conversations",
}

# 旧库 schema 对应的基线迁移版本：
# 存量库的表结构等价于该迁移已应用的状态。
# 以后每次发布新迁移，若涉及对存量数据的结构变更，保持此值不变即可——
# 新迁移会作为 upgrade 的一部分被执行。
_LEGACY_BASELINE_REVISION = "0001_initial"


def _legacy_needs_stamp(db_path: str) -> bool:
    """判断是否为旧库：无 alembic_version 表但存在旧业务表。"""
    try:
        conn = sqlite3.connect(db_path, timeout=10)
        try:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            tables = {r[0] for r in rows}
        finally:
            conn.close()
    except sqlite3.Error:
        logger.exception(f"检查旧库状态失败: {db_path}")
        return False
    return "alembic_version" not in tables and bool(tables & _LEGACY_BUSINESS_TABLES)


def _run_migrations() -> None:
    """同步执行 alembic 迁移（供 to_thread 调用，勿在事件循环中直接执行）。

    - 旧库先 stamp 到 _LEGACY_BASELINE_REVISION：把存量 schema 标记为
      基线已应用，基线之后的新迁移会随 upgrade 被执行。
    - 新库直接 upgrade head，从头建表。
    """
    from alembic import command
    from alembic.config import Config

    migrations_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migrations")
    cfg = Config(os.path.join(migrations_dir, "alembic.ini"))
    # env.py 自行解析数据库 URL（paths.data_path），这里清空 ini 里的残留值
    cfg.set_main_option("sqlalchemy.url", "")

    db_path = _get_db_path()
    if os.path.isfile(db_path) and _legacy_needs_stamp(db_path):
        logger.info(
            f"检测到旧数据库（无 alembic_version），"
            f"执行 alembic stamp {_LEGACY_BASELINE_REVISION} 标记基线"
        )
        command.stamp(cfg, _LEGACY_BASELINE_REVISION)

    command.upgrade(cfg, "head")
    logger.info("数据库迁移完成 (alembic upgrade head)")


async def init_db():
    """初始化数据库：建连 → 迁移 → seed"""
    global _engine, _async_session_factory, _initialized

    with _lock:
        if _initialized:
            return

        db_url = _get_db_url()
        logger.info(f"初始化消息数据库: {db_url}")

        # 迁移（同步 IO，放线程池避免阻塞事件循环；此时服务未开放，无并发写）
        await asyncio.to_thread(_run_migrations)

        # 创建异步引擎
        _engine = create_async_engine(
            db_url,
            echo=False,
            future=True,
        )

        # 创建会话工厂
        _async_session_factory = sessionmaker(
            bind=_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        # 初始化数据（幂等）
        from server.db.seed import run_seeds
        await run_seeds()

        _initialized = True
        logger.info("消息数据库初始化完成")


async def close_db():
    """关闭数据库连接"""
    global _engine, _async_session_factory, _initialized
    
    with _lock:
        if _engine is not None:
            await _engine.dispose()
            _engine = None
            _async_session_factory = None
            _initialized = False
            logger.info("消息数据库连接已关闭")


def get_session() -> AsyncSession:
    """获取数据库会话"""
    if _async_session_factory is None:
        raise RuntimeError("数据库未初始化，请先调用 init_db()")
    return _async_session_factory()
