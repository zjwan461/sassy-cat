# -*- coding: utf-8 -*-
"""
数据库连接和会话管理。

使用 SQLAlchemy 异步引擎 + aiosqlite 驱动。
数据库文件位于用户数据目录下的 messages.sqlite。
"""

import logging
import threading

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

import paths
from server.db.models import Base

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


async def init_db():
    """初始化数据库连接和表结构"""
    global _engine, _async_session_factory, _initialized
    
    with _lock:
        if _initialized:
            return
        
        db_url = _get_db_url()
        logger.info(f"初始化消息数据库: {db_url}")
        
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
        
        # 创建表结构
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
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
