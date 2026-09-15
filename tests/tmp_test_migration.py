# -*- coding: utf-8 -*-
"""临时验证脚本：DB migration + seed 机制。

用法: python tests/tmp_test_migration.py
使用临时数据目录，不影响真实用户数据。验证三件事：
  1. 全新库：alembic upgrade head 建出全部表 + seed 数据
  2. 旧库（无 alembic_version 但有业务表）：自动 stamp head，且 0002 迁移补上 system_meta
  3. 二次 init_db：幂等，不重复 stamp/seed 出错
"""

import asyncio
import os
import shutil
import sqlite3
import sys
import tempfile

# 临时数据目录
_TMP_DATA_DIR = tempfile.mkdtemp(prefix="sassy-cat-migtest-")
os.environ["SASSY_CAT_DATA_DIR"] = _TMP_DATA_DIR

_PY_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "python"))
if _PY_ROOT not in sys.path:
    sys.path.insert(0, _PY_ROOT)

from paths import data_path  # noqa: E402

DB_PATH = data_path("messages.sqlite")


def _tables() -> set:
    conn = sqlite3.connect(DB_PATH)
    try:
        return {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
    finally:
        conn.close()


def _alembic_version() -> str | None:
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute("SELECT version_num FROM alembic_version").fetchall()
        return rows[0][0] if rows else None
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()


def make_legacy_db() -> None:
    """模拟旧库：用 create_all 建出 0001 时代的四张表（不含 system_meta，无 alembic_version）"""
    from sqlalchemy import create_engine
    from server.db.models import Base

    engine = create_engine(f"sqlite:///{DB_PATH}")
    legacy_tables = [
        Base.metadata.tables["messages"],
        Base.metadata.tables["attachments"],
        Base.metadata.tables["knowledge_bases"],
        Base.metadata.tables["kb_documents"],
    ]
    for t in legacy_tables:
        t.create(engine)
    engine.dispose()


async def main() -> int:
    from server.db.database import init_db, close_db, get_session
    from sqlalchemy import select
    from server.db.models import SystemMeta, KnowledgeBase
    from server.db.seed import DEFAULT_KB_ID

    # ===== 场景 1：全新库 =====
    print("=== 场景1: 全新库 ===")
    assert not os.path.exists(DB_PATH)
    await init_db()
    tables = _tables()
    print("tables:", sorted(tables))
    assert {"messages", "attachments", "knowledge_bases", "kb_documents",
            "system_meta", "alembic_version"} <= tables, "新库表结构不完整"
    assert _alembic_version() == "0002_system_meta", f"version={_alembic_version()}"

    # 验证 seed 数据
    async with get_session() as session:
        row = (await session.execute(
            select(SystemMeta).where(SystemMeta.key == "schema_seed_version")
        )).scalar_one()
        assert row.value == "1", row.value
        print("seed ok: schema_seed_version =", row.value)
        kb = (await session.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == DEFAULT_KB_ID)
        )).scalar_one()
        assert kb.name == "default", kb.name
        print("seed ok: default kb =", kb.id, kb.name)
    await close_db()

    # ===== 场景 2：旧库 =====
    print("=== 场景2: 旧库自动 stamp + 补迁移 ===")
    os.remove(DB_PATH)
    make_legacy_db()
    tables = _tables()
    assert "alembic_version" not in tables and "system_meta" not in tables
    await init_db()
    tables = _tables()
    print("tables:", sorted(tables))
    assert "system_meta" in tables, "旧库升级后应补出 system_meta"
    assert _alembic_version() == "0002_system_meta", f"version={_alembic_version()}"
    async with get_session() as session:
        row = (await session.execute(
            select(SystemMeta).where(SystemMeta.key == "schema_seed_version")
        )).scalar_one()
        assert row.value == "1"
        print("seed ok (legacy)  schema_seed_version =", row.value)
    await close_db()

    # 模拟用户改名后重启：seed 不应覆盖用户数据（幂等且不回写）
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE knowledge_bases SET name='my-kb' WHERE id=?", (DEFAULT_KB_ID,))
    conn.commit()
    conn.close()

    # ===== 场景 3：幂等重启（迁移与 seed 均不应重复执行出错）=====
    print("=== 场景3: 幂等重启 ===")
    await init_db()
    async with get_session() as session:
        cnt = (await session.execute(select(SystemMeta))).scalars().all()
        print("system_meta rows:", [(r.key, r.value) for r in cnt])
        kb = (await session.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == DEFAULT_KB_ID)
        )).scalar_one()
        assert kb.name == "my-kb", f"seed 不应覆盖用户改名: {kb.name}"
        print("default kb name 保持用户改名:", kb.name)
    await close_db()

    # 再来一次完整重启确认幂等
    await init_db()
    await close_db()
    print("ALL PASSED")
    return 0


if __name__ == "__main__":
    try:
        code = asyncio.run(main())
    finally:
        shutil.rmtree(_TMP_DATA_DIR, ignore_errors=True)
    sys.exit(code)
