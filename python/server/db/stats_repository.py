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

import json
import logging
import time
from datetime import datetime, timedelta

from sqlalchemy import Integer, cast, func, select

from server.db.database import get_session
from server.db.models import Conversation, KbDocument, KnowledgeBase, Message
import config_loader

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


async def usage_stats(session_limit: int = 8) -> dict:
    """按模型 / 会话聚合 token、耗时与失败率。

    模型名与耗时从 0008 迁移新增的 messages.model / duration_ms 读取；
    老消息没有这两列，模型归入「历史未记录」，耗时跳过。
    """
    async with get_session() as session:
        rows = (
            await session.execute(
                select(
                    Message.session_id,
                    Message.model,
                    Message.usage_metadata,
                    Message.duration_ms,
                    Message.error,
                    Message.created_at,
                ).where(Message.role == "assistant")
            )
        ).all()
        conv_rows = (
            await session.execute(select(Conversation.id, Conversation.title))
        ).all()

    titles = {cid: title for cid, title in conv_rows}
    models: dict[str, dict] = {}
    sessions: dict[str, dict] = {}

    for session_id, model, usage_text, duration_ms, error, created_at in rows:
        try:
            usage = json.loads(usage_text) if usage_text else {}
        except (TypeError, ValueError):
            usage = {}
        inp = int(usage.get("input_tokens") or 0)
        out = int(usage.get("output_tokens") or 0)
        duration = int(duration_ms) if duration_ms is not None else None
        failed = bool(error)

        model_key = (model or "").strip() or "历史未记录"
        for bucket, key in (
            (models, model_key),
            (sessions, session_id),
        ):
            item = bucket.setdefault(
                key,
                {
                    "turns": 0,
                    "inputTokens": 0,
                    "outputTokens": 0,
                    "durationTotal": 0,
                    "durationCount": 0,
                    "errors": 0,
                    "lastAt": 0,
                },
            )
            item["turns"] += 1
            item["inputTokens"] += inp
            item["outputTokens"] += out
            if duration is not None:
                item["durationTotal"] += duration
                item["durationCount"] += 1
            if failed:
                item["errors"] += 1
            item["lastAt"] = max(item["lastAt"], int(created_at or 0))

    def finalize(item: dict) -> dict:
        turns = item["turns"]
        return {
            "turns": turns,
            "inputTokens": item["inputTokens"],
            "outputTokens": item["outputTokens"],
            "totalTokens": item["inputTokens"] + item["outputTokens"],
            "avgDurationMs": (
                round(item["durationTotal"] / item["durationCount"])
                if item["durationCount"]
                else None
            ),
            "errors": item["errors"],
            "failureRate": round(item["errors"] / turns, 4) if turns else 0,
            "lastAt": item["lastAt"],
        }

    model_list = [
        {"model": name, **finalize(data)}
        for name, data in sorted(
            models.items(), key=lambda kv: kv[1]["inputTokens"] + kv[1]["outputTokens"], reverse=True
        )
    ]
    session_list = [
        {
            "sessionId": sid,
            "title": titles.get(sid) or "未命名对话",
            **finalize(data),
        }
        for sid, data in sorted(
            sessions.items(), key=lambda kv: kv[1]["inputTokens"] + kv[1]["outputTokens"], reverse=True
        )[:session_limit]
    ]

    total_turns = sum(i["turns"] for i in models.values())
    total_input = sum(i["inputTokens"] for i in models.values())
    total_output = sum(i["outputTokens"] for i in models.values())
    total_errors = sum(i["errors"] for i in models.values())
    durations = sum(i["durationTotal"] for i in models.values())
    duration_counts = sum(i["durationCount"] for i in models.values())

    return {
        "summary": {
            "turns": total_turns,
            "inputTokens": total_input,
            "outputTokens": total_output,
            "totalTokens": total_input + total_output,
            "errors": total_errors,
            "failureRate": round(total_errors / total_turns, 4) if total_turns else 0,
            "avgDurationMs": round(durations / duration_counts) if duration_counts else None,
        },
        "models": model_list,
        "sessions": session_list,
    }


def _estimate_tokens(text: str | None) -> int:
    """没有 provider usage 时的粗略 token 估算：CJK 约 1.5 字/token，其余约 4 字符/token。"""
    if not text:
        return 0
    cjk = 0
    for ch in text:
        if "\u4e00" <= ch <= "\u9fff" or "\u3040" <= ch <= "\u30ff":
            cjk += 1
    other = len(text) - cjk
    return int(cjk / 1.5 + other / 4)


async def session_stats(session_id: str) -> dict:
    """当前会话底部统计：轮次/步数、Token、缓存命中、输出速度与上下文占用。

    部分 OpenAI-compatible 服务不返回 usage；此时按正文字符估算并标记 estimated，
    保证速度/上下文至少可用，前端会加 ≈ 提示。
    """
    async with get_session() as session:
        rows = (
            await session.execute(
                select(
                    Message.role,
                    Message.usage_metadata,
                    Message.tool_calls,
                    Message.tool_call_args,
                    Message.tool_call_result,
                    Message.content,
                    Message.reasoning,
                    Message.duration_ms,
                    Message.ttft_ms,
                    Message.decode_ms,
                    Message.model,
                    Message.created_at,
                )
                .where(Message.session_id == session_id)
                .order_by(Message.created_at.asc())
            )
        ).all()

    turns = 0
    steps = 0
    input_tokens = 0
    output_tokens = 0
    cache_read = 0
    duration_ms = 0
    latest_usage: dict = {}
    latest_model = None
    estimated_context = 0
    estimated_output = 0
    last_output_tokens = 0
    last_duration_ms = 0
    last_decode_ms = 0
    last_ttft_ms = 0

    for (
        role,
        usage_text,
        tool_calls_text,
        tool_args_text,
        tool_result_text,
        content,
        reasoning,
        row_duration,
        row_ttft,
        row_decode,
        model,
        _created_at,
    ) in rows:
        text_for_context = "\n".join(
            x for x in (content, reasoning, tool_args_text, tool_result_text) if x
        )
        estimated_context += _estimate_tokens(text_for_context)

        if role == "user":
            turns += 1
        if role != "assistant":
            continue

        steps += 1
        try:
            calls = json.loads(tool_calls_text) if tool_calls_text else []
            if isinstance(calls, list):
                steps += len(calls)
        except (TypeError, ValueError):
            pass

        estimated_output += _estimate_tokens("\n".join(x for x in (content, reasoning) if x))

        try:
            usage = json.loads(usage_text) if usage_text else {}
        except (TypeError, ValueError):
            usage = {}
        last_output_tokens = int(usage.get("output_tokens") or 0) if usage else 0
        if not last_output_tokens:
            last_output_tokens = _estimate_tokens("\n".join(x for x in (content, reasoning) if x))
        last_duration_ms = int(row_duration or 0)
        last_decode_ms = int(row_decode or 0)
        last_ttft_ms = int(row_ttft or 0)
        if usage:
            latest_usage = usage
            input_tokens += int(usage.get("input_tokens") or 0)
            output_tokens += int(usage.get("output_tokens") or 0)
            details = usage.get("input_token_details") or {}
            cache_read += int(details.get("cache_read") or 0)
        if row_duration is not None:
            duration_ms += int(row_duration)
        if model:
            latest_model = model

    # 上下文窗口取当前激活配置档；老配置没有该字段时给一个保守默认值
    context_window = 131072
    try:
        llm = config_loader.current().get("llm") or {}
        active = llm.get("activeProfile") or "default"
        profile = (llm.get("profiles") or {}).get(active) or {}
        context_window = int(profile.get("contextWindow") or context_window)
    except Exception:
        pass

    estimated = input_tokens == 0 and output_tokens == 0 and estimated_output > 0
    if estimated:
        # 加上系统提示词/工具 schema 的大致固定开销，避免上下文百分比低得不真实
        input_tokens = estimated_context + 3000
        output_tokens = estimated_output

    context_tokens = (
        int(latest_usage.get("total_tokens") or 0)
        if not estimated
        else estimated_context + 3000
    )
    speed = (
        round(last_output_tokens / (last_decode_ms / 1000), 1)
        if last_decode_ms > 100 and last_output_tokens > 0
        else None
    )
    return {
        "sessionId": session_id,
        "turns": turns,
        "steps": steps,
        "inputTokens": input_tokens,
        "outputTokens": output_tokens,
        "totalTokens": input_tokens + output_tokens,
        "cacheReadTokens": cache_read,
        "cacheHitRate": round(cache_read / input_tokens, 4) if input_tokens and not estimated else None,
        "durationMs": duration_ms,
        "ttftMs": last_ttft_ms or None,
        "decodeMs": last_decode_ms or None,
        "tokensPerSecond": speed,
        "contextTokens": context_tokens,
        "contextWindow": context_window,
        "contextPercent": (
            round(context_tokens / context_window * 100, 1) if context_window else None
        ),
        "model": latest_model,
        "estimated": estimated,
    }
