# -*- coding: utf-8 -*-
"""
会话（对话）元数据管理：SQLite 持久化（conversations 表）。

- 存储位置：消息数据库 messages.sqlite（server/db），conversations.json 时代已结束，
  旧数据由 seed（server/db/seed.py::seed_import_conversations）一次性导入
- 消息本体由 message_repository / LangGraph checkpointer 按 session_id（即 thread_id）
  持久化，本模块只存会话级关键信息：id、标题、创建/更新时间
- 激活会话 id 存于 system_meta 表（key = ACTIVE_KEY），任何时刻保证有激活会话
- 所有对外函数为 async，复用 server.db 的异步会话，失败时抛异常由调用方处理
"""

import logging
import time
import uuid

from sqlalchemy import delete as sa_delete, func, select, update

from server.db.database import get_session
from server.db.models import Conversation, SystemMeta

logger = logging.getLogger(__name__)

# system_meta 中记录激活会话 id 的键（seed 导入旧数据时同样引用此键）
ACTIVE_KEY = "active_conversation_id"
DEFAULT_TITLE = "新对话"
TITLE_MAX = 24  # 自动标题取首条用户消息前 N 字符


def _now_ms() -> int:
    return int(time.time() * 1000)


def _new_id() -> str:
    return "conv-" + uuid.uuid4().hex[:12]


def _to_dict(conv: Conversation) -> dict:
    """转换为前端使用的字段结构（camelCase），与旧 conversations.json 保持一致。"""
    return {
        "id": conv.id,
        "title": conv.title,
        "createdAt": conv.created_at,
        "updatedAt": conv.updated_at,
    }


async def _read_active_id(session) -> str | None:
    meta = (
        await session.execute(select(SystemMeta).where(SystemMeta.key == ACTIVE_KEY))
    ).scalar_one_or_none()
    return meta.value if meta else None


async def _write_active_id(session, conv_id: str) -> None:
    meta = (
        await session.execute(select(SystemMeta).where(SystemMeta.key == ACTIVE_KEY))
    ).scalar_one_or_none()
    if meta is None:
        session.add(SystemMeta(key=ACTIVE_KEY, value=conv_id, updated_at=_now_ms()))
    else:
        meta.value = conv_id
        meta.updated_at = _now_ms()


async def _latest_id(session) -> str | None:
    """最近更新一条会话的 id（activeId 悬空/缺失时的回退目标）。"""
    return (
        await session.execute(
            select(Conversation.id).order_by(Conversation.updated_at.desc()).limit(1)
        )
    ).scalar_one_or_none()


async def _ensure_active() -> str:
    """保证任何时刻存在有效激活会话：悬空则回退最近更新，全空则新建默认会话。"""
    async with get_session() as session:
        active = await _read_active_id(session)
        if active and (
            await session.execute(
                select(Conversation.id).where(Conversation.id == active)
            )
        ).scalar_one_or_none():
            return active
        fallback = await _latest_id(session)
        if fallback is None:
            conv = Conversation(
                id=_new_id(), title=DEFAULT_TITLE, created_at=_now_ms(), updated_at=_now_ms()
            )
            session.add(conv)
            fallback = conv.id
        await _write_active_id(session, fallback)
        await session.commit()
        return fallback


# ---------------- 对外 API（均为异步函数） ----------------

async def list_sorted() -> list[dict]:
    """全部会话，按 updatedAt 倒序（列表页展示顺序）。"""
    async with get_session() as session:
        rows = (
            await session.execute(
                select(Conversation).order_by(Conversation.updated_at.desc())
            )
        ).scalars().all()
        return [_to_dict(c) for c in rows]


async def list_page(page: int = 1, page_size: int = 20) -> tuple[list[dict], int]:
    """分页查询会话（按 updatedAt 倒序），返回 (items, total)。

    offset/limit 分页供前端无限滚动加载更多；total 用于判定是否还有下一页。
    """
    page = max(1, int(page or 1))
    page_size = max(1, int(page_size or 20))
    async with get_session() as session:
        total = (
            await session.execute(select(func.count()).select_from(Conversation))
        ).scalar() or 0
        rows = (
            await session.execute(
                select(Conversation)
                .order_by(Conversation.updated_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars().all()
        return [_to_dict(c) for c in rows], total


async def active_id() -> str:
    """当前激活会话 id（不存在或悬空则自动修复/创建）。"""
    return await _ensure_active()


async def get(conv_id: str) -> dict | None:
    async with get_session() as session:
        conv = (
            await session.execute(
                select(Conversation).where(Conversation.id == conv_id)
            )
        ).scalar_one_or_none()
        return _to_dict(conv) if conv else None


async def create(title: str = DEFAULT_TITLE, activate: bool = True) -> dict:
    """新建会话；默认置为激活。返回新会话对象。"""
    now = _now_ms()
    conv = Conversation(id=_new_id(), title=title, created_at=now, updated_at=now)
    async with get_session() as session:
        session.add(conv)
        if activate:
            await _write_active_id(session, conv.id)
        await session.commit()
    return _to_dict(conv)


async def set_active(conv_id: str) -> dict | None:
    """切换激活会话；id 不存在返回 None。"""
    async with get_session() as session:
        conv = (
            await session.execute(
                select(Conversation).where(Conversation.id == conv_id)
            )
        ).scalar_one_or_none()
        if conv is None:
            return None
        await _write_active_id(session, conv_id)
        await session.commit()
        return _to_dict(conv)


async def touch(conv_id: str) -> None:
    """更新会话 updatedAt（每轮消息调用，驱动列表排序）。"""
    async with get_session() as session:
        await session.execute(
            update(Conversation)
            .where(Conversation.id == conv_id)
            .values(updated_at=_now_ms())
        )
        await session.commit()


async def rename(conv_id: str, title: str) -> dict | None:
    """重命名会话（手动改名或首条消息自动生成标题）。"""
    title = (title or "").strip()[:TITLE_MAX] or DEFAULT_TITLE
    async with get_session() as session:
        conv = (
            await session.execute(
                select(Conversation).where(Conversation.id == conv_id)
            )
        ).scalar_one_or_none()
        if conv is None:
            return None
        conv.title = title
        await session.commit()
        return _to_dict(conv)


async def auto_title(conv_id: str, first_user_text: str) -> dict | None:
    """新会话首条用户消息 -> 截断生成标题（仅当仍是默认标题时生效，避免覆盖手动改名）。

    返回：标题确实发生变更时返回更新后的会话；未变更（已有自定义标题）返回 None。
    """
    conv = await get(conv_id)
    if conv is not None and conv.get("title") in (DEFAULT_TITLE, ""):
        return await rename(conv_id, (first_user_text or "").strip()[:TITLE_MAX] or DEFAULT_TITLE)
    return None


async def delete(conv_id: str) -> bool:
    """删除会话元数据（checkpoint 与消息数据保留在 sqlite，不物理删除）。

    删除的是激活会话时，自动切换到最近更新的其他会话；列表空了则新建默认会话。
    返回是否真实删除；切换后的 activeId 用 active_id() 再取。
    """
    async with get_session() as session:
        result = await session.execute(
            sa_delete(Conversation).where(Conversation.id == conv_id)
        )
        if result.rowcount == 0:
            return False
        if await _read_active_id(session) == conv_id:
            fallback = await _latest_id(session)
            if fallback is None:
                conv = Conversation(
                    id=_new_id(),
                    title=DEFAULT_TITLE,
                    created_at=_now_ms(),
                    updated_at=_now_ms(),
                )
                session.add(conv)
                fallback = conv.id
            await _write_active_id(session, fallback)
        await session.commit()
        return True
