# -*- coding: utf-8 -*-
"""
提醒事项工具层：暴露给 Agent 的 @tool 集合。

与纯数据层 reminders.py 分离，保持 builtin_tools.py 精简。
数据读写统一走 agent 共享 SqliteStore（与用户画像同库）。

注意：数据层函数统一用 `_` 前缀别名导入，避免 @tool 装饰后的同名
StructuredTool 对象遮蔽模块内的数据函数（否则工具内部调用会触发
"StructuredTool' object is not callable"）。
"""

from langchain.tools import tool

from agent.reminders import _now_ms
from agent.reminders import add_reminder as _add_reminder
from agent.reminders import cancel_reminder as _cancel_reminder
from agent.reminders import describe_repeat as _describe_repeat
from agent.reminders import format_time as _format_time
from agent.reminders import list_reminders as _list_reminders
from agent.reminders import mark_done as _mark_done
from agent.reminders import parse_time_text as _parse_time_text


@tool
def create_reminder(
    content: str,
    at: str | None = None,
    in_minutes: int | None = None,
    repeat: str = "none",
    repeat_every: int | None = None,
    repeat_unit: str | None = None,
    repeat_until: str | None = None,
) -> str:
    """创建/设置一条定时提醒。设置后会由桌宠在约定时间提醒主人。

    触发场景（出现以下意图时应调用，无需征求同意）：
    - 一次性提醒："5分钟后提醒我关火"、"下午3点提醒我开会"、"明天9点提醒我交报告"
    - 重复提醒："每天早上8点提醒我喝水"、"每周五下午提醒我周报"、"每2小时提醒我起来活动"

    参数说明：
    - content: 提醒的内容（必填，尽量简洁）。
    - at: 绝对触发时间，格式如 "2026-08-21 15:30:00" 或 "2026-08-21 15:30"。
      相对时间优先用 in_minutes，例如"5分钟后"应传 in_minutes=5 而非手算 at。
      需要"明天/下周"之类相对日期时，先调用 get_date_time 获取当前时间自行推算绝对时间。
    - in_minutes: 相对分钟数（从当前时刻起多少分钟后提醒），与 at 二选一，优先用这个。
    - repeat: 重复规则：
      - "none": 一次性（默认）
      - "daily": 每天同一时刻
      - "weekly": 每周同一时刻
      - "interval": 自定义间隔，需配合 repeat_every + repeat_unit
    - repeat_every: repeat="interval" 时的步长数值，如 2
    - repeat_unit: repeat="interval" 时的单位："minute"|"hour"|"day"|"week"，
      如 (repeat_every=2, repeat_unit="hour") 表示每2小时
    - repeat_until: 重复提醒的截止时间（可选），格式同 at，超过后不再提醒。

    返回设置结果；若时间解析失败或已过期会返回错误，请修正参数后重试。
    """
    content = (content or "").strip()
    if not content:
        return "错误：提醒内容不能为空。"

    repeat = repeat or "none"
    if repeat not in ("none", "daily", "weekly", "interval"):
        return f"错误：repeat 仅支持 none/daily/weekly/interval，收到：{repeat}"
    if repeat == "interval":
        if not repeat_every or repeat_every < 1:
            return "错误：repeat=interval 时必须提供 repeat_every（>=1）和 repeat_unit。"
        if repeat_unit not in ("minute", "hour", "day", "week"):
            return f"错误：repeat_unit 仅支持 minute/hour/day/week，收到：{repeat_unit}"

    # 触发时间：优先 in_minutes（相对），其次 at（绝对）
    next_at = None
    if in_minutes is not None and in_minutes > 0:
        next_at = int(_now_ms() + in_minutes * 60 * 1000)
    elif at:
        next_at = _parse_time_text(at)
        if next_at is None:
            return (
                f"错误：无法解析时间 {at!r}。请使用如 '2026-08-21 15:30' 的格式，"
                f"或改用 in_minutes 传入相对分钟数。"
            )

    if next_at is None:
        return "错误：必须提供 at（绝对时间）或 in_minutes（相对分钟数）之一。"

    if next_at <= _now_ms():
        return (
            f"错误：提醒时间 {_format_time(next_at)} 已过期。"
            f"当前时间为 {_format_time(_now_ms())}，请重新确定时间。"
        )

    until = _parse_time_text(repeat_until) if repeat_until else None

    rec = _add_reminder(
        content=content,
        next_at=next_at,
        repeat=repeat,
        repeat_every=repeat_every if repeat == "interval" else None,
        repeat_unit=repeat_unit if repeat == "interval" else None,
        repeat_until=until,
    )
    suffix = ""
    if repeat != "none":
        suffix = f"，重复规则：{_describe_repeat(rec)}"
        if until:
            suffix += f"，截止 {_format_time(until)}"
    return f"提醒已设置✅：{rec['content']}，触发时间 {_format_time(rec['next_at'])}{suffix}。id={rec['id']}"


@tool
def list_reminders(status: str = "active") -> str:
    """列出当前已有的提醒事项。

    status 参数：
    - "active": 待触发的提醒（默认）
    - "done": 已完成/已触发的提醒
    - "cancelled": 已取消的提醒
    - "all": 全部

    当主人询问"我有哪些提醒/还有什么待办提醒/提醒我什么"时调用。
    返回包含每条提醒的 id、内容、触发时间、重复规则与状态，供后续按 id 完成或取消。
    """
    status = (status or "active").strip().lower()
    if status not in ("active", "done", "cancelled", "all"):
        return f"错误：status 仅支持 active/done/cancelled/all，收到：{status}"

    records = _list_reminders(status=None if status == "all" else status)
    if not records:
        return f"当前没有{('' if status in ('all', 'active') else status)}提醒。"

    lines = []
    for r in records:
        lines.append(
            f"- [{r['id']}] {r['content']} | 时间：{_format_time(r.get('next_at'))}"
            f" | 重复：{_describe_repeat(r)} | 状态：{r.get('status')}"
        )
    return "\n".join(lines)


@tool
def complete_reminder(reminder_id: str) -> str:
    """把一条提醒标记为已完成（一次性提醒通常触发后会自动完成；此工具用于主人表示"已经处理完"时手动确认完成，完成后不再触发）。

    reminder_id 从 list_reminders 的结果中获取（形如 rm-xxxxxxxxxxxx）。
    若是重复提醒，不建议直接完成，而应改用 cancel_reminder。
    """
    reminder_id = (reminder_id or "").strip()
    if not reminder_id:
        return "错误：缺少 reminder_id。可先调用 list_reminders 查看已有提醒的 id。"
    ok = _mark_done(reminder_id)
    if ok:
        return f"提醒 {reminder_id} 已标记为完成 ✅。"
    return f"错误：未找到活跃的提醒 {reminder_id}，可能已被完成或取消。可先调用 list_reminders 确认。"


@tool
def cancel_reminder(reminder_id: str) -> str:
    """取消一条提醒（包括一次性与重复提醒），取消后不再触发。

    reminder_id 从 list_reminders 的结果中获取（形如 rm-xxxxxxxxxxxx）。
    当主人说"取消XX提醒/删掉XX提醒/不用提醒我XX了"时调用。
    """
    reminder_id = (reminder_id or "").strip()
    if not reminder_id:
        return "错误：缺少 reminder_id。可先调用 list_reminders 查看已有提醒的 id。"
    ok = _cancel_reminder(reminder_id)
    if ok:
        return f"提醒 {reminder_id} 已取消 ✅，之后不会再提醒。"
    return f"错误：未找到提醒 {reminder_id}，可能已被取消。可先调用 list_reminders 确认。"