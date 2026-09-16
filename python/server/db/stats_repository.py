# -*- coding: utf-8 -*-
"""
Dashboard 报表统计聚合查询：

- 对话次数：messages 表 role='user' 的消息条数（今日 / 历史）
- Token 用量：assistant 消息 usage_metadata JSON 字段（input/output/total，今日 / 历史）
- 知识库规模：knowledge_bases / kb_documents 计数与 chunk_count 汇总
- 近 N 天趋势：按本地时区逐日聚合对话次数与 Token 总量

created_at 存毫秒时间戳，SQLite 侧用 json_extract 提取 token 字段，
时间分桶用 (created_at + tz_offset_ms) / 86400000 的"天序号"聚合，避免逐行函数转换。
"""

import logging
import time
from datetime import datetime, timedelta

from sqlalchemy import Integer, cast, func, select

from server.db.database import get_session
from server.db.models import KbDocument, KnowledgeBase, Message

logger = logging.getLogger(__name__)

# 本地时区相对 UTC 的偏移（秒），进程内计算一次即可（桌面单机场景）
_TZ_OFFSET_SEC = -time.localtime().tm_gmtoff


def _local_day_start_ms(days_ago: int = 0) -> int:
    """本地时区 days_ago 天前零点的毫秒时间戳。"""
    now = datetime.now()
    midnight = (now - timedelta(days=days_ago)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return int(midnight.timestamp() * 1000)


def _day_no(ms: int) -> int:
    """毫秒时间戳 -> 本地时区"天序号"（用于分组聚合）。"""
    return (ms + _TZ_OFFSET_SEC * 1000) // 86_400_000


# usage_metadata 中 token 字段的 json_extract 聚合表达式（NULL 行自动被 SUM 忽略）
def _token_sum_expr(key: str):
    return func.coalesce(
        func.sum(
            cast(func.json_extract(Message.usage_metadata, f"$.{key}"), Integer)
        ),
        0,
    )


async def _token_sums_since(start_ms: int | None) -> dict:
    """汇总 usage_metadata 中 input/output token（start_ms 为 None 时统计全部历史）。

    total 由 input + output 求和得出，避免依赖 total_tokens 字段是否一定存在。
    """
    async with get_session() as session:
        stmt = select(
            _token_sum_expr("input_tokens"),
            _token_sum_expr("output_tokens"),
        ).where(
            Message.role == "assistant",
            Message.usage_metadata.isnot(None),
        )
        if start_ms is not None:
            stmt = stmt.where(Message.created_at >= start_ms)
        row = (await session.execute(stmt)).one()
    inp, out = int(row[0] or 0), int(row[1] or 0)
    return {"inputTokens": inp, "outputTokens": out, "totalTokens": inp + out}


async def _user_msg_count(start_ms: int | None) -> int:
    """role='user' 消息条数（start_ms 为 None 时统计全部历史）。"""
    async with get_session() as session:
        stmt = select(func.count(Message.id)).where(Message.role == "user")
        if start_ms is not None:
            stmt = stmt.where(Message.created_at >= start_ms)
        return int((await session.execute(stmt)).scalar() or 0)


async def _daily_trend(days: int) -> list[dict]:
    """近 N 天（含今日）逐日聚合：对话次数 + Token 总量。

    一次查出窗口内全部 user 消息与 assistant usage 的 (created_at, tokens)，
    Python 侧按本地天序号分桶，避免 SQL 内复杂的时区换算。
    """
    start_ms = _local_day_start_ms(days - 1)
    day_no_start = _day_no(start_ms)

    async with get_session() as session:
        chat_rows = (
            await session.execute(
                select(Message.created_at).where(
                    Message.role == "user", Message.created_at >= start_ms
                )
            )
        ).scalars().all()
        tok_rows = (
            await session.execute(
                select(
                    Message.created_at,
                    func.json_extract(Message.usage_metadata, "$.input_tokens"),
                    func.json_extract(Message.usage_metadata, "$.output_tokens"),
                ).where(
                    Message.role == "assistant",
                    Message.usage_metadata.isnot(None),
                    Message.created_at >= start_ms,
                )
            )
        ).all()

    buckets: dict[int, dict] = {}
    for i in range(days):
        d = _local_day_start_ms(days - 1 - i)
        buckets[_day_no(d)] = {
            "date": datetime.fromtimestamp(d / 1000).strftime("%m-%d"),
            "chats": 0,
            "tokens": 0,
        }
    for created_at in chat_rows:
        b = buckets.get(_day_no(created_at))
        if b:
            b["chats"] += 1
    for created_at, tin, tout in tok_rows:
        b = buckets.get(_day_no(created_at))
        if b:
            b["tokens"] += int(tin or 0) + int(tout or 0)
    return [buckets[k] for k in sorted(buckets)]


async def _kb_stats() -> dict:
    """知识库个数 / 文档总数 / 分片总数，以及按库分布明细（供堆叠柱图）。"""
    async with get_session() as session:
        kb_count = int(
            (await session.execute(select(func.count(KnowledgeBase.id)))).scalar() or 0
        )
        doc_count = int(
            (await session.execute(select(func.count(KbDocument.id)))).scalar() or 0
        )
        chunk_count = int(
            (
                await session.execute(
                    select(func.coalesce(func.sum(KbDocument.chunk_count), 0))
                )
            ).scalar()
            or 0
        )
        per_kb_rows = (
            await session.execute(
                select(
                    KnowledgeBase.name,
                    func.count(KbDocument.id),
                    func.coalesce(func.sum(KbDocument.chunk_count), 0),
                )
                .outerjoin(KbDocument, KbDocument.kb_id == KnowledgeBase.id)
                .group_by(KnowledgeBase.id)
                .order_by(KnowledgeBase.created_at.desc())
            )
        ).all()

    per_kb = [
        {"name": name, "docCount": int(dc or 0), "chunkCount": int(cc or 0)}
        for name, dc, cc in per_kb_rows
    ]
    return {
        "kbCount": kb_count,
        "docCount": doc_count,
        "chunkCount": int(chunk_count),
        "perKb": per_kb,
    }


async def dashboard_stats(trend_days: int = 7) -> dict:
    """Dashboard 报表一次性聚合响应。"""
    today_start = _local_day_start_ms(0)
    return {
        "serverTimeMs": int(time.time() * 1000),
        "todayStartMs": today_start,
        "chat": {
            "today": await _user_msg_count(today_start),
            "total": await _user_msg_count(None),
        },
        "token": {
            "today": await _token_sums_since(today_start),
            "total": await _token_sums_since(None),
        },
        "kb": await _kb_stats(),
        "trend": await _daily_trend(trend_days),
    }
