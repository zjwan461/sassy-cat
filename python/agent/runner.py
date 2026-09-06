# -*- coding: utf-8 -*-
"""
Agent 流式运行器：在独立线程消费 langgraph agent.stream，
经 janus 队列桥接回 asyncio 事件循环，产出结构化事件。

事件类型（dict）：
  {"kind": "delta", "text": str}                    # 流式 token
  {"kind": "tool", "name": str, "phase": "start"}   # 工具调用开始
  {"kind": "interrupt", "payload": dict}            # 高危操作待确认
  {"kind": "done", "text": str}                     # 本轮结束（最终全文）
  {"kind": "error", "message": str}                 # 异常
"""

import asyncio
import logging
import threading

import janus
from langgraph.types import Command

from agent.engine import holder

logger = logging.getLogger(__name__)


def _extract_item(item: dict):
    """从 content_blocks 首个块解析事件，返回 dict 或 None"""
    t = item.get("type")
    if t == "text":
        return {"kind": "delta", "text": item.get("text", "")}
    if t == "tool_call_chunk":
        if item.get("id"):  # 每个工具调用的首块携带 id
            return {"kind": "tool", "name": item.get("name"), "phase": "start"}
    return None


def _worker_stream(agent, input_payload, config, q: janus.Queue, cancel: threading.Event):
    """在线程内运行阻塞的 agent.stream，事件推入 q.sync_q"""
    final_parts = []
    try:
        for _, chunk in agent.stream(
            input_payload,
            config=config,
            stream_mode="messages",
            subgraphs=True,
        ):
            if cancel.is_set():
                logger.info("收到取消信号，终止流")
                break
            msg_chunk = chunk[0]
            cb = msg_chunk.content_blocks
            if not cb:
                continue
            event = _extract_item(cb[0])
            if event is None:
                continue
            if event["kind"] == "delta":
                final_parts.append(event["text"])
            q.sync_q.put(event)

        # 流结束后检查是否停在 interrupt（待确认）
        if not cancel.is_set():
            try:
                state = agent.get_state(config)
                if state.next:  # 存在待执行节点 => 被 interrupt 挂起
                    interrupts = []
                    for task in state.tasks:
                        for itr in getattr(task, "interrupts", []) or []:
                            interrupts.append(getattr(itr, "value", None))
                    if interrupts:
                        q.sync_q.put({"kind": "interrupt", "payload": {"actions": interrupts}})
                        q.sync_q.put({"kind": "done", "text": "".join(final_parts)})
                        return
            except Exception as e:
                logger.warning(f"检查 interrupt 状态失败: {e}")

        q.sync_q.put({"kind": "done", "text": "".join(final_parts)})
    except Exception as e:
        logger.exception("agent.stream 异常")
        q.sync_q.put({"kind": "error", "message": str(e)})


async def run_turn(user_text: str, thread_id: str, cancel_event: threading.Event):
    """发起新一轮对话，异步产出事件"""
    version, agent = holder.get()
    q = janus.Queue()
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 50}
    payload = {"messages": [{"role": "user", "content": user_text}]}
    thread = threading.Thread(
        target=_worker_stream, args=(agent, payload, config, q, cancel_event), daemon=True
    )
    thread.start()
    try:
        while True:
            event = await q.async_q.get()
            yield event
            if event["kind"] in ("done", "error"):
                break
    finally:
        q.close()


async def resume_turn(thread_id: str, approved: bool, cancel_event: threading.Event):
    """用户对 interrupt 确认后恢复执行（仅对当前仍挂起的 thread 有效）"""
    version, agent = holder.get()
    q = janus.Queue()
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 50}
    decision = "approve" if approved else "reject"
    payload = Command(resume={"decisions": [{"type": decision}]})
    thread = threading.Thread(
        target=_worker_stream, args=(agent, payload, config, q, cancel_event), daemon=True
    )
    thread.start()
    try:
        while True:
            event = await q.async_q.get()
            yield event
            if event["kind"] in ("done", "error"):
                break
    finally:
        q.close()
