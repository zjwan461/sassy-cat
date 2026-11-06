# -*- coding: utf-8 -*-
"""会话轮次串行化 + 消息序列化回归测试（无需 LLM）。

覆盖：
- server.ws_agent._begin_turn：同一会话的上一轮被取消并等待收尾后才开新轮
- server.db.message_repository._message_to_dict：JSON 字段被解码成数组/对象，
  脏数据不抛异常

运行：
    .venv\\Scripts\\python.exe tests\\tmp_test_turn_serial.py
"""
import asyncio
import os
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "python"))

from server import ws_agent  # noqa: E402
from server.db import message_repository as repo  # noqa: E402

FAILED = []


def check(name, cond, detail=""):
    mark = "PASS" if cond else "FAIL"
    if not cond:
        FAILED.append(name)
    print(f"[{mark}] {name}" + (f"  | {detail}" if detail else ""))


class FakeMessage:
    """模拟 ORM Message（只用到 _message_to_dict 读取的字段）。"""

    id = "m1"
    session_id = "conv-1"
    role = "assistant"
    content = "hi"
    reasoning = None
    tool_calls = '[{"tool_name": "execute"}]'
    tool_call_args = '["{}"]'
    created_at = 1
    interrupt_actions = '[{"name": "delete"}]'
    interrupt_decisions = '[{"type": "approve"}]'
    tool_call_result = '[{"tool_call_id": "c1", "text": "ok"}]'
    usage_metadata = '{"total_tokens": 3}'
    error = ""
    subagent_name = None
    segments = '[{"agent": "dsh", "text": "x"}]'
    attachments = []


class DirtyMessage(FakeMessage):
    interrupt_actions = "not-json{"
    segments = ""


async def test_serialization():
    d = repo._message_to_dict(FakeMessage())
    check("toolCalls 解码为 list", isinstance(d["toolCalls"], list), type(d["toolCalls"]).__name__)
    check("interruptActions 解码为 list", isinstance(d["interruptActions"], list), type(d["interruptActions"]).__name__)
    check("interruptDecisions 解码为 list", isinstance(d["interruptDecisions"], list))
    check("toolCallResult 解码为 list", isinstance(d["toolCallResult"], list))
    check("usageMetadata 解码为 dict", isinstance(d["usageMetadata"], dict))
    check("segments 解码为 list", isinstance(d["segments"], list))

    dirty = repo._message_to_dict(DirtyMessage())
    check("脏 JSON 降级为原文而不是抛异常", dirty["interruptActions"] == "not-json{", repr(dirty["interruptActions"]))
    check("空字符串字段返回 None", dirty["segments"] is None, repr(dirty["segments"]))


async def test_begin_turn_serializes():
    session = "conv-serial"
    ws_agent._session_cancel.clear()
    ws_agent._session_turn_tasks.clear()

    order = []
    first_cancel = threading.Event()

    async def first_turn():
        # 模拟上一轮：被取消后需要一点时间收尾
        ws_agent._session_cancel[session] = first_cancel
        ws_agent._session_turn_tasks[session] = asyncio.current_task()
        for _ in range(40):
            if first_cancel.is_set():
                break
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.05)  # 收尾（落库）耗时
        order.append("first-done")

    async def second_turn():
        await asyncio.sleep(0.02)  # 保证 first 先登记
        cancel = threading.Event()
        await ws_agent._begin_turn(session, cancel)
        order.append("second-start")

    t1 = asyncio.create_task(first_turn())
    t2 = asyncio.create_task(second_turn())
    await asyncio.wait([t1, t2], timeout=5)

    check("上一轮收到取消信号", first_cancel.is_set())
    check("新轮在上一轮收尾之后才开始", order == ["first-done", "second-start"], str(order))
    check("登记的是新轮的取消事件", ws_agent._session_cancel.get(session) is not first_cancel)

    ws_agent._session_cancel.clear()
    ws_agent._session_turn_tasks.clear()


async def main():
    await test_serialization()
    await test_begin_turn_serializes()
    print()
    print(f"共 {len(FAILED)} 个失败" if FAILED else "全部通过")
    return 1 if FAILED else 0


sys.exit(asyncio.run(main()))