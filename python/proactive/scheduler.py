# -*- coding: utf-8 -*-
"""
主动提醒调度器（设计稿第 6 节）。

活动信号来源：Electron 主进程 powerMonitor 经 WS 上行 client.event {name:'user_activity'}。
规则：闲置 >= thresholdMinutes 且距上次提醒 >= quietPeriodMinutes -> 推送提醒；
锁屏/息屏暂停计时；当前 session 正在流式对话时跳过。

文案一期使用模板池随机；二期可接 LLM 按人设生成。
"""

import asyncio
import logging
import random
import time

import config_loader
from server import bus
from server.protocol import envelope

logger = logging.getLogger(__name__)

REMIND_POOL = [
    "为什么不理本喵😾",
    "喵～你还在吗？都忘了这里还有只猫了…",
    "再不理我，本喵就睡着了💤",
    "工作再忙，也要摸一下猫呀！",
    "哼，本喵大人有大量，再给你一次撸猫的机会。",
]

# 调度轮询间隔（秒）
TICK_INTERVAL = 30


class ActivityState:
    """全局活动状态（由 ws_agent 收到 client.event 时更新）"""

    def __init__(self):
        self.last_active_ts = time.time()
        self.last_remind_ts = 0.0
        self.screen_locked = False

    def ping(self):
        now = time.time()
        if self.screen_locked:
            self.screen_locked = False  # 活动信号即解锁
        self.last_active_ts = now

    def lock(self):
        self.screen_locked = True

    def unlock(self):
        self.screen_locked = False
        self.last_active_ts = time.time()


state = ActivityState()


def register_hub_listener():
    """提醒文案发布走事件总线：定向到 pet 所在房间不可知，一期广播给所有连接"""


async def tick_once():
    """单轮检查（由 app lifespan 周期任务调用）"""
    cfg = config_loader.current()
    idle_cfg = cfg.get("pet.idleReminder", {}) or {}
    if not idle_cfg.get("enabled", True):
        return
    if state.screen_locked:
        return

    threshold = float(idle_cfg.get("thresholdMinutes", 30)) * 60
    quiet = float(idle_cfg.get("quietPeriodMinutes", 10)) * 60
    now = time.time()

    idle = now - state.last_active_ts
    since_remind = now - state.last_remind_ts
    if idle >= threshold and since_remind >= quiet:
        text = random.choice(REMIND_POOL)
        state.last_remind_ts = now
        logger.info(f"触发闲置提醒（idle={int(idle)}s）: {text}")
        await bus.hub.publish_all(envelope("proactive.message", {
            "msgId": f"pr-{int(now)}",
            "text": text,
            "urgency": "normal",
        }))
        await bus.hub.publish_all(envelope("pet.command", {
            "action": "remind",
            "durationMs": 8000,
            "text": text,
        }))


async def run_forever(stop_event):
    """周期任务入口：sleep 与 stop 等待并行，避免忙等"""
    logger.info(f"proactive 调度器启动，轮询间隔 {TICK_INTERVAL}s")
    while not stop_event.is_set():
        try:
            await tick_once()
        except Exception:
            logger.exception("proactive tick 异常")
        # asyncio.Event.wait() 不支持 timeout，用 wait_for 包裹实现"等待或超时"
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=TICK_INTERVAL)
        except asyncio.TimeoutError:
            pass
        except Exception:
            logger.exception("proactive wait 异常")
            pass
        print("[pro] after wait", flush=True)
