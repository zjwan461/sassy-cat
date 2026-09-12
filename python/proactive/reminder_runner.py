# -*- coding: utf-8 -*-
"""
提醒事项触发调度器：轮询到点提醒并推送给桌宠。

- 存储：agent 共享 SqliteStore（见 agent.reminders），读取为同步 sqlite3，
  统一经 asyncio.to_thread 包装，避免阻塞事件循环。
- 触发：next_at <= now 且 status=active 的提醒。
- 推送：proactive.reminder（结构化事件） + pet.command{action:"remind"}（桌宠气泡动画）。
- 关键帧后调用 advance_after_fire：一次性 -> done；重复 -> 推进 next_at 到未来。

配置（config.user.json，Settings 页可改，保存后热生效）：
  pet.reminders.pollIntervalSeconds  轮询间隔（秒），3~30，默认 5
  pet.reminders.bubbleDurationMs     气泡显示时长（毫秒），3000~30000，默认 8000
"""

import asyncio
import logging
import time

import config_loader
from server import bus
from server.protocol import envelope

from agent.reminders import advance_after_fire, due_reminders

logger = logging.getLogger(__name__)

# 轮询间隔钳制范围（秒）
POLL_MIN = 3
POLL_MAX = 30
POLL_DEFAULT = 5

# 气泡显示时长钳制范围（毫秒）
BUBBLE_MIN_MS = 3000
BUBBLE_MAX_MS = 30000
BUBBLE_DEFAULT_MS = 8000


def _poll_interval() -> float:
    """读取轮询间隔（秒），非法值回退默认并钳制在 3~30s。每次调用实时读取，支持热更新。"""
    cfg = config_loader.current()
    try:
        v = float(cfg.get("pet.reminders.pollIntervalSeconds", POLL_DEFAULT))
    except (TypeError, ValueError):
        v = POLL_DEFAULT
    if v != v or v in (float("inf"), float("-inf")):  # NaN / Inf 防护
        v = POLL_DEFAULT
    return max(POLL_MIN, min(POLL_MAX, v))


def _bubble_duration_ms() -> int:
    """读取气泡显示时长（毫秒），非法值回退默认并钳制在 3000~30000ms。"""
    cfg = config_loader.current()
    try:
        v = int(cfg.get("pet.reminders.bubbleDurationMs", BUBBLE_DEFAULT_MS))
    except (TypeError, ValueError):
        v = BUBBLE_DEFAULT_MS
    return max(BUBBLE_MIN_MS, min(BUBBLE_MAX_MS, v))


async def _due_and_fire_once() -> int:
    """检查并触发一次到点提醒，返回本次触发的条数。"""
    now_ms = int(time.time() * 1000)
    due = await asyncio.to_thread(due_reminders, now_ms)
    if not due:
        return 0

    duration_ms = _bubble_duration_ms()
    fired = 0
    for rec in due:
        text = f"⏰ {rec.get('content', '')}"
        reminder_id = rec.get("id", "")
        await bus.hub.publish_all(
            envelope(
                "proactive.reminder",
                {
                    "msgId": f"pr-{int(now_ms)}-{reminder_id}",
                    "reminderId": reminder_id,
                    "text": text,
                    "content": rec.get("content", ""),
                    "durationMs": duration_ms,
                },
            )
        )
        await bus.hub.publish_all(
            envelope(
                "pet.command",
                {"action": "remind", "durationMs": duration_ms, "text": text},
            )
        )
        # 推进重复计划 / 完结一次性提醒（同步 sqlite 写入，to_thread 包装）
        await asyncio.to_thread(advance_after_fire, rec, now_ms)
        fired += 1
        logger.info(f"提醒已触发: id={reminder_id} content={rec.get('content')}")

    return fired


async def tick_once():
    """单轮检查（由 run_forever 周期调用）"""
    try:
        fired = await _due_and_fire_once()
        if fired:
            logger.info(f"本轮触发 {fired} 条提醒")
    except Exception:
        logger.exception("reminder tick 异常")


async def run_forever(stop_event: asyncio.Event):
    """周期任务入口：sleep 与 stop 等待并行，避免忙等。间隔每轮实时读取，支持配置热更新。"""
    logger.info(f"提醒调度器启动，默认轮询间隔 {POLL_DEFAULT}s（可配置 3~30s）")
    while not stop_event.is_set():
        await tick_once()
        interval = _poll_interval()
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass
        except Exception:
            logger.exception("reminder wait 异常")
            pass