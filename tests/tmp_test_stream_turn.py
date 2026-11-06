# -*- coding: utf-8 -*-
"""_stream_turn 事件处理回归测试（无需数据库与 LLM）。

用假事件流驱动 server.ws_agent._stream_turn，校验：
- delta 按 50ms/80 字符节流合并，且 buffer 计数正确
- 来源切换（主 agent <-> 子 agent）会切断帧
- tool_args 归属到发起它的那次调用
- interrupt 的 actions 解析对空/缺字段安全
- usage 只落最后一份
- done / error / 取消三条路径都会落库，且字段口径一致

运行：
    .venv\\Scripts\\python.exe tests\\tmp_test_stream_turn.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "python"))

from server import ws_agent  # noqa: E402

FAILED = []


def check(name, cond, detail=""):
    mark = "PASS" if cond else "FAIL"
    if not cond:
        FAILED.append(name)
    print(f"[{mark}] {name}" + (f"  | {detail}" if detail else ""))


class FakeHub:
    def __init__(self):
        self.frames = []

    async def publish_all(self, frame, exclude=None):
        self.frames.append(frame)

    async def publish(self, session_id, frame, exclude=None):
        self.frames.append(frame)


async def run_case(name, events, *, cancel=False):
    """跑一轮，返回 (frames, persisted_kwargs_list)。"""
    hub = FakeHub()
    persisted = []

    orig_hub = ws_agent.hub
    orig_persist = ws_agent._save_or_update_assistant_message_sage
    orig_spawn = ws_agent._spawn

    async def fake_persist(**kwargs):
        persisted.append(kwargs)

    def fake_spawn(coro, name=""):
        # 立即调度协程但不 await（与真实实现一致：后台执行）
        return asyncio.ensure_future(coro)

    ws_agent.hub = hub
    ws_agent._save_or_update_assistant_message_sage = fake_persist
    ws_agent._spawn = fake_spawn

    async def gen():
        for e in events:
            yield e

    cancel_event = ws_agent.threading.Event()
    if cancel:
        # 让生成器结束前就置位，模拟"用户点停止"
        async def gen_cancelled():
            for e in events:
                yield e
            cancel_event.set()
        gen_impl = gen_cancelled()
    else:
        gen_impl = gen()

    try:
        await ws_agent._stream_turn(None, "conv-test", gen_impl, "msg-1", cancel_event)
        await asyncio.sleep(0.15)  # 等后台落库任务跑完
    finally:
        ws_agent.hub = orig_hub
        ws_agent._save_or_update_assistant_message_sage = orig_persist
        ws_agent._spawn = orig_spawn

    return hub.frames, persisted


def types_of(frames):
    return [f["type"] if isinstance(f, dict) else f for f in frames]


async def main():
    # ---- 1. delta 合并 + 来源切换 ----
    frames, _ = await run_case("delta", [
        {"kind": "delta", "text": "你"},
        {"kind": "delta", "text": "好"},
        {"kind": "delta", "text": "子代理说", "agent": "dsh"},
        {"kind": "done", "text": "你好子代理说"},
    ])
    deltas = [f for f in frames if f["type"] == "chat.delta"]
    check("delta 被合并（不带 agent 的两段合并为一帧）", len(deltas) >= 2, f"frames={len(deltas)}")
    check("主 agent 文本合并且无 agent 字段", deltas[0]["payload"].get("agent") is None and "你好" in deltas[0]["payload"]["text"], str(deltas[0]["payload"])[:60])
    check("子 agent 文本带 agent 标记", any(d["payload"].get("agent") == "dsh" for d in deltas))

    # ---- 2. tool / tool_args / tool_message ----
    frames, persisted = await run_case("tool", [
        {"kind": "tool", "name": "execute", "phase": "start", "tool_call_id": "call-1"},
        {"kind": "tool_args", "args": '{"command":'},
        {"kind": "tool_args", "args": '"dir"}'},
        {"kind": "tool_message", "text": "ok", "tool_call_id": "call-1"},
        {"kind": "done", "text": ""},
    ])
    tool_frames = [f for f in frames if f["type"] == "agent.tool_call"]
    check("tool_call 帧带 toolCallId", tool_frames and tool_frames[0]["payload"]["toolCallId"] == "call-1")
    check("tool 参数落库归属到该次调用", persisted and 'dir' in (persisted[0]["tool_call_args"][0] or ""), str(persisted[0]["tool_call_args"])[:60])
    check("工具结果落库", persisted and persisted[0]["tool_call_result"] and persisted[0]["tool_call_result"][0]["tool_call_id"] == "call-1")

    # ---- 3. interrupt：actions 缺字段/空/None 都不能崩 ----
    frames, persisted = await run_case("interrupt", [
        {"kind": "interrupt", "payload": {"actions": [{"action_requests": [{"name": "delete"}, {"name": "execute"}]}]}},
        {"kind": "done", "text": ""},
    ])
    check("interrupt 帧下发", any(f["type"] == "agent.interrupt" for f in frames))
    check("interrupt 记录 2 个待确认项", persisted and len(persisted[0]["interrupt_actions"] or []) == 2, str(persisted[0]["interrupt_actions"])[:80])

    frames, persisted = await run_case("interrupt-empty", [
        {"kind": "interrupt", "payload": {"actions": []}},
        {"kind": "interrupt", "payload": {}},
        {"kind": "interrupt", "payload": {"actions": [{}]}},
        {"kind": "done", "text": ""},
    ])
    check("空/缺字段 interrupt 不抛异常", any(f["type"] == "chat.completed" for f in frames), types_of(frames))

    # ---- 4. usage 取最后一个 ----
    frames, persisted = await run_case("usage", [
        {"kind": "usage", "usage_metadata": {"total_tokens": 10}},
        {"kind": "usage", "usage_metadata": {"total_tokens": 99}},
        {"kind": "done", "text": "x"},
    ])
    check("usage 落库取最后一份", persisted and persisted[0]["usage_metadata"]["total_tokens"] == 99, str(persisted[0]["usage_metadata"]))

    # ---- 5. error 路径落库 ----
    frames, persisted = await run_case("error", [
        {"kind": "delta", "text": "半截"},
        {"kind": "error", "code": "rate_limit", "message": "请求过于频繁"},
    ])
    check("error 帧下发", any(f["type"] == "chat.error" for f in frames))
    check("error 轮次落库并带错误标记", persisted and persisted[0]["error"] == "请求过于频繁" and "半截" in persisted[0]["content"], str(persisted[0]["error"]))

    # ---- 6. 取消路径落库 ----
    frames, persisted = await run_case("cancel", [
        {"kind": "delta", "text": "停止前的内容"},
    ], cancel=True)
    check("取消后仍广播 chat.completed", any(f["type"] == "chat.completed" for f in frames), types_of(frames))
    check("取消轮次落库已产出内容", persisted and "停止前的内容" in (persisted[0]["content"] or ""), str(persisted[:1])[:100])

    print()
    print(f"共 {len(FAILED)} 个失败" if FAILED else "全部通过")
    return 1 if FAILED else 0


sys.exit(asyncio.run(main()))