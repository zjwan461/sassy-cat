# -*- coding: utf-8 -*-
"""
数据库初始化数据（seed）模块。

在迁移（migration）之后执行，向数据库写入/维护必要的初始数据。
每个 seed 函数必须幂等（重复执行结果一致），由 run_seeds() 统一调度，
运行时机与顺序在此维护。
"""

import json
import logging
import os
import time

from sqlalchemy import func, select

from server.db.database import get_session
from server.db.models import Conversation, KnowledgeBase, SystemMeta

logger = logging.getLogger(__name__)

# 应用侧标记当前 schema 对应的版本号（与 alembic 的 revision 无关，
# 供业务代码/前端读取"数据版本号"做兼容判断）。
SCHEMA_SEED_VERSION = "1"

# 默认知识库：存放聊天上传文件自动 embedding 的内容。
# id 固定，供业务代码引用（不要通过 name 查找，用户可改名）。
DEFAULT_KB_ID = "default"
DEFAULT_KB_NAME = "default"
DEFAULT_KB_DESCRIPTION = "聊天上传文件自动向量化后的默认存放处"


def _now_ms() -> int:
    return int(time.time() * 1000)


async def seed_system_meta() -> None:
    """写入系统元数据（幂等：按 key upsert）"""
    rows = [
        # 可在此追加更多初始键值对，例如默认配置、欢迎信息版本号等
        ("schema_seed_version", SCHEMA_SEED_VERSION),
        ("app_created_at", str(_now_ms())),  # 仅首次写入生效（下面用 not exists 语义）
    ]

    async with get_session() as session:
        for key, value in rows:
            existing = (
                await session.execute(select(SystemMeta).where(SystemMeta.key == key))
            ).scalar_one_or_none()

            if existing is None:
                session.add(SystemMeta(key=key, value=value, updated_at=_now_ms()))
                logger.info(f"seed: system_meta 新增 {key}={value}")
            elif key == "app_created_at":
                # 首装时间戳永不覆盖
                continue
            elif existing.value != value:
                existing.value = value
                existing.updated_at = _now_ms()
                logger.info(f"seed: system_meta 更新 {key}={value}")
        await session.commit()


async def seed_default_kb() -> None:
    """铺底默认知识库（id 固定为 DEFAULT_KB_ID）。

    幂等策略：仅首次插入；已存在时不覆盖 name/description，
    因为用户可能在设置里自行改名，时间戳也保持原始值。
    """
    async with get_session() as session:
        existing = (
            await session.execute(
                select(KnowledgeBase).where(KnowledgeBase.id == DEFAULT_KB_ID)
            )
        ).scalar_one_or_none()

        if existing is not None:
            return  # 已存在（含用户改过名的情况），保持不动

        now = _now_ms()
        session.add(
            KnowledgeBase(
                id=DEFAULT_KB_ID,
                name=DEFAULT_KB_NAME,
                description=DEFAULT_KB_DESCRIPTION,
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()
        logger.info(f"seed: 已创建默认知识库 id={DEFAULT_KB_ID}")


async def seed_import_conversations() -> None:
    """一次性导入旧 conversations.json 的会话元数据到 conversations 表。

    幂等策略：仅当 conversations 表为空且旧文件存在时执行导入；
    导入成功后把旧文件改名为 conversations.json.imported.bak，
    之后启动不再触碰。文件缺失/损坏则跳过（业务侧会自动铺底默认会话）。
    """
    import paths
    from server.conversations import ACTIVE_KEY

    json_path = paths.data_path("conversations.json")
    if not os.path.isfile(json_path):
        return  # 无旧数据（新装或已导入过）

    async with get_session() as session:
        count = (
            await session.execute(select(func.count()).select_from(Conversation))
        ).scalar() or 0
        if count > 0:
            return  # 表已有数据，不重复导入

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"旧 conversations.json 解析失败，跳过导入: {e}")
            return

        convs = raw.get("conversations") if isinstance(raw, dict) else None
        if not convs:
            os.replace(json_path, json_path + ".imported.bak")
            logger.info("seed: 旧 conversations.json 为空，已改名归档")
            return

        now = _now_ms()
        for c in convs:
            cid = c.get("id")
            if not cid:
                continue
            session.add(
                Conversation(
                    id=cid,
                    title=c.get("title") or "新对话",
                    created_at=c.get("createdAt") or now,
                    updated_at=c.get("updatedAt") or now,
                )
            )
        active_id = raw.get("activeId")
        valid_ids = {c.get("id") for c in convs if c.get("id")}
        if active_id in valid_ids:
            session.add(
                SystemMeta(key=ACTIVE_KEY, value=active_id, updated_at=now)
            )
        await session.commit()

        os.replace(json_path, json_path + ".imported.bak")
        logger.info(f"seed: 已导入旧会话 {len(convs)} 条，conversations.json 归档为 .imported.bak")


async def run_seeds() -> None:
    """执行全部 seed（在 migration 之后调用）。

    每个 seed 独立 try/except：单个失败只记 error 不阻断启动，
    避免初始化数据问题导致整个服务起不来。
    """
    seeds = [seed_system_meta, seed_default_kb, seed_import_conversations]
    for seed in seeds:
        try:
            await seed()
        except Exception:
            logger.exception(f"seed {seed.__name__} 执行失败")
    logger.info("数据库 seed 执行完成")
