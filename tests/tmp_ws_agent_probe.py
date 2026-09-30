# -*- coding: utf-8 -*-
"""临时探测：_stream_turn 按来源分段下发 chat.delta（用完可删）。

验证三点：
1) 主 agent 与子 agent（agent=dsh）的增量不会混进同一帧
2) 带来源的帧携带 agent 字段，不带来源的帧不携带
3) 同源累积达到阈值时照常节流 flush
"""

import asyncio
import os
import sys
import threading

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "python"))

from server import ws_agent  # noqa: E402

frames = []


async def fake_publish(room, frame, exclude=None):
    frames.append(frame)


async def fake_save(**kwargs):
    return None


ws_agent.hub.publish = fake_publish  # 拦下 fan-out
ws_agent._save_or_update_assistant_message_sage = fake_save  # 跳过落库


async def gen():
    yield {"kind": "delta", "text": "喵"}
    yield {"kind": "delta", "text": "，本喵在。"}
    yield {"kind": "delta", "text": "dsh start handle", "agent": "dsh"}
    yield {"kind": "delta", "text": "好的", "agent": "dsh"}
    yield {"kind": "delta", "text": "以上。"}  # 回到主 agent
    yield {"kind": "delta", "text": "x" * 100, "agent": "dsh"}  # 触发节流 flush
    yield {"kind": "done", "text": "全文"}


asyncio.run(ws_agent._stream_turn(None, "s1", gen(), "m1", threading.Event()))

for frame in frames:
    print(frame["type"], frame["payload"])