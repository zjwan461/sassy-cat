# -*- coding: utf-8 -*-
"""
提醒事项数据层与领域逻辑（基于 agent 共享 SqliteStore，与用户画像同库）。

命名空间：("reminders", USER_ID)
value 结构（JSON 兼容）：
{
  "id": "rm-...",
  "content": str,                 # 提醒内容
  "created_at": int,              # 创建时间戳 (毫秒)
  "next_at": int,                 # 下次触发时间戳 (毫秒)
  "repeat": "none"|"daily"|"weekly"|"interval",
  "repeat_every": int|None,       # repeat==interval 时的步长
  "repeat_unit": str|None,        # "minute"|"hour"|"day"|"week"
  "repeat_until": int|None,       # 重复截止时间戳 (毫秒)，可选
  "status": "active"|"done"|"cancelled",
  "last_fired_at": int|None       # 上次触发时间戳 (毫秒)
}

repeat 语义：
- none:     一次性，触发后置为 done
- daily:    每日（next_at += 24h）
- weekly:   每周（next_at += 7d）
- interval: 每 repeat_every * repeat_unit 触发一次

说明：SqliteStore.search 的 query 是向量语义搜索（本项目未配 embedding），
且 filter 无法做范围查询，因此"到期判断"采用全量拉取 + 内存过滤。
个人桌面应用数据量极小，无性能问题。
"""

import logging
import time
import uuid
from datetime import datetime

from agent.constant import USER_ID

logger = logging.getLogger(__name__)

NAMESPACE = ("reminders", USER_ID)
SEARCH_LIMIT = 500

_REPEAT_UNIT_SECONDS = {
    "minute": 60,
    "hour": 3600,
    "day": 86400,
    "week": 604800,
}

_REPEAT_UNIT_CN = {
    "minute": "分钟",
    "hour": "小时",
    "day": "天",
    "week": "周",
}

_TIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d",
    "%Y/%m/%d",
)


def _store():
    """惰性获取共享 SqliteStore 单例（函数内 import，避免与 engine 顶层 import 形成环）"""
    from agent.engine import get_store

    return get_store()


def _now_ms() -> int:
    return int(time.time() * 1000)


def _new_id() -> str:
    return "rm-" + uuid.uuid4().hex[:12]


def _update(rec: dict) -> None:
    """把一条提醒记录写回 store（put 整体覆盖）"""
    _store().put(NAMESPACE, rec["id"], rec, index=False)


# ====================== 时间解析 / 格式化 ======================

def parse_time_text(text: str) -> int | None:
    """解析时间字符串为毫秒时间戳，支持常见格式；失败返回 None"""
    text = (text or "").strip()
    if not text:
        return None
    for fmt in _TIME_FORMATS:
        try:
            return int(datetime.strptime(text, fmt).timestamp() * 1000)
        except ValueError:
            continue
    return None


def format_time(ms: int | None) -> str:
    """毫秒时间戳 -> 可读字符串"""
    if not ms:
        return "-"
    return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M")


def describe_repeat(rec: dict) -> str:
    """把重复规则渲染成人类可读文字"""
    r = rec.get("repeat") or "none"
    if r == "daily":
        return "每天"
    if r == "weekly":
        return "每周"
    if r == "interval":
        every = rec.get("repeat_every") or 1
        unit = (rec.get("repeat_unit") or "hour").lower()
        unit_cn = _REPEAT_UNIT_CN.get(unit, unit)
        return f"每{every}{unit_cn}"
    return "一次性"


# ====================== CRUD ======================

def add_reminder(
    content: str,
    next_at: int,
    repeat: str = "none",
    repeat_every: int | None = None,
    repeat_unit: str | None = None,
    repeat_until: int | None = None,
) -> dict:
    """创建一条提醒，返回持久化后的记录（含 id）"""
    rid = _new_id()
    rec = {
        "id": rid,
        "content": (content or "").strip(),
        "created_at": _now_ms(),
        "next_at": int(next_at),
        "repeat": repeat or "none",
        "repeat_every": repeat_every,
        "repeat_unit": repeat_unit,
        "repeat_until": int(repeat_until) if repeat_until else None,
        "status": "active",
        "last_fired_at": None,
    }
    _update(rec)
    logger.info(f"提醒已创建: id={rid} content={rec['content']} next_at={rec['next_at']}")
    return rec


def get_reminder(rid: str) -> dict | None:
    """按 id 读取提醒记录；不存在返回 None"""
    it = _store().get(NAMESPACE, rid)
    if it is None or not getattr(it, "value", None):
        return None
    return dict(it.value)


def list_reminders(status: str | None = None, limit: int = SEARCH_LIMIT) -> list[dict]:
    """列出全部提醒（按 next_at 升序），可按 status 过滤（active/done/cancelled）"""
    items = _store().search(NAMESPACE, limit=limit)
    out = []
    for it in items:
        value = getattr(it, "value", None)
        if not value:
            continue
        rec = dict(value)
        if status and rec.get("status") != status:
            continue
        out.append(rec)
    out.sort(key=lambda r: r.get("next_at") or 0)
    return out


def due_reminders(now_ms: int | None = None) -> list[dict]:
    """当前已到触发时间的 active 提醒列表（next_at <= now）"""
    now = now_ms or _now_ms()
    out = []
    for rec in list_reminders(status="active"):
        nxt = rec.get("next_at")
        if nxt is not None and nxt <= now:
            out.append(rec)
    return out


def mark_done(rid: str) -> bool:
    """把一条提醒标记为已完成（不再触发）。成功返回 True"""
    rec = get_reminder(rid)
    if not rec or rec.get("status") != "active":
        return False
    rec["status"] = "done"
    _update(rec)
    logger.info(f"提醒完成: id={rid}")
    return True


def cancel_reminder(rid: str) -> bool:
    """取消一条仍处于 active 的提醒（不再触发）。成功返回 True"""
    rec = get_reminder(rid)
    if not rec or rec.get("status") != "active":
        return False
    rec["status"] = "cancelled"
    _update(rec)
    logger.info(f"提醒已取消: id={rid}")
    return True


# ====================== 重复规则推进 ======================

def _repeat_step(rec: dict) -> int:
    """返回单次重复的步长（毫秒）；不重复/非法规则返回 0"""
    r = rec.get("repeat")
    if r == "daily":
        return 24 * 3600 * 1000
    if r == "weekly":
        return 7 * 24 * 3600 * 1000
    if r == "interval":
        every = rec.get("repeat_every") or 1
        unit = (rec.get("repeat_unit") or "hour").lower()
        secs = _REPEAT_UNIT_SECONDS.get(unit, 3600)
        return max(1, int(every)) * secs * 1000
    return 0


def advance_after_fire(rec: dict, now_ms: int | None = None) -> dict:
    """提醒触发后推进重复计划：

    - 一次性：state -> done
    - 重复：把 next_at 推进到 future（错过多个周期也仅补发本次，避免连环补发）；
      超过 repeat_until 则置为 done。
    返回更新后的记录。
    """
    now = now_ms or _now_ms()
    rec["last_fired_at"] = rec.get("next_at")

    step = _repeat_step(rec)
    if step <= 0:
        rec["status"] = "done"
        _update(rec)
        return rec

    next_at = rec.get("next_at") or 0
    until = rec.get("repeat_until")
    while next_at <= now:
        next_at += step
        if until and next_at > until:
            rec["status"] = "done"
            _update(rec)
            return rec
    rec["next_at"] = next_at
    _update(rec)
    logger.info(f"提醒已推进: id={rec['id']} next_at={next_at}")
    return rec