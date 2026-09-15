# -*- coding: utf-8 -*-
"""Alembic 迁移环境配置。

- 数据库路径统一由 paths.data_path("messages.sqlite") 解析，
  运行时自动迁移与 CLI 手动迁移使用同一份配置，行为一致。
- SQLite 下开启 render_as_batch=True（batch 模式），
  否则加 NOT NULL 列 / 改类型 / 删列 / 删表等 DDL 无法生成。
"""

import logging
import os
import sys

from sqlalchemy import engine_from_config, pool, inspect
from alembic import context

# 确保 python/ 目录在 sys.path（alembic.ini 的 prepend_sys_path 已设置 ../../..，
# 此处兜底，兼容 IDE 中直接调用 env 的场景）
_HERE = os.path.dirname(os.path.abspath(__file__))
_PY_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
if _PY_ROOT not in sys.path:
    sys.path.insert(0, _PY_ROOT)

from paths import data_path  # noqa: E402
from server.db.models import Base  # noqa: E402

config = context.config

# 注意：这里【不能】调用 logging.config.fileConfig(alembic.ini)。
# fileConfig 会整体重建根 logger 的 handler（清掉应用侧注册的 ProtocolLogHandler 等），
# 导致迁移之后所有应用日志不再经 __PROTOCOL__ 通道推送到前端日志页。
# 改为：仅当根 logger 无任何 handler（独立 CLI 运行 alembic）时做 basicConfig 兜底；
# 嵌入应用运行时，alembic 日志经 propagate 走应用已有的 handler 体系。
if not logging.root.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format='%(levelname)-5.5s [%(name)s] %(message)s',
        datefmt='%H:%M:%S',
        stream=sys.stderr,
    )

target_metadata = Base.metadata


def _get_url() -> str:
    """统一解析数据库 URL（同步驱动，迁移专用）。"""
    return f"sqlite:///{data_path('messages.sqlite')}"


def run_migrations_offline() -> None:
    """离线模式：只生成 SQL 脚本，不连库（alembic revision --sql 使用）。"""
    context.configure(
        url=_get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：连接数据库执行迁移。"""
    section = config.get_section(config.config_ini_section, {})
    engine = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        url=_get_url(),
    )
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
