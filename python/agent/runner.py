# -*- coding: utf-8 -*-
"""
Agent 流式运行器：在独立线程消费 langgraph agent.stream，
经 janus 队列桥接回 asyncio 事件循环，产出结构化事件。

事件类型（dict）：
  {"kind": "delta", "text": str}                    # 流式 token
  {"kind": "tool", "name": str, "phase": "start"}   # 工具调用开始
  {"kind": "tool_args", "args": str}                # 工具参数增量片段（JSON 分片流）
  {"kind": "interrupt", "payload": dict}            # 高危操作待确认
  {"kind": "done", "text": str}                     # 本轮结束（最终全文）
  {"kind": "error", "message": str}                 # 异常
"""

import asyncio
import logging
import threading

import janus
from langgraph.types import Command
from langchain.messages import AIMessageChunk, ToolMessage

import config_loader
from agent.engine import holder

logger = logging.getLogger(__name__)


def _recursion_limit() -> int:
    """从运行时配置读取单轮最大递归步数（优先从 active profile 读取，兼容旧顶层 agent 段），非法值回退为 50"""
    cfg = config_loader.current()
    try:
        return max(1, int(cfg.active_agent_config().get("recursionLimit", 50)))
    except (TypeError, ValueError, AttributeError):
        return 50


def _extract_item(item: dict, msg_chunk):
    if isinstance(msg_chunk, AIMessageChunk):
        """从单个 content_block 解析事件，返回 list[dict]（可能为空）"""
        t = item.get("type")
        if t == "text":
            return [{"kind": "delta", "text": item.get("text", "")}]
        if t == "tool_call_chunk":
            events = []
            if item.get("id"):  # 每个工具调用的首块携带 id 与 name
                events.append(
                    {
                        "kind": "tool",
                        "name": item.get("name"),
                        "phase": "start",
                        "tool_call_id": item.get("id"),
                    }
                )
            # 后续块携带 args 增量片段（不完整的 JSON 字符串分片），透传给前端流式拼接
            args_part = item.get("args")
            if args_part:
                events.append({"kind": "tool_args", "args": args_part})
            return events
        if t == "reasoning":
            text = item.get("reasoning") or ""
            # langchain 对 reasoning_content 仅判 is not None，正文阶段会产出空串块，过滤之
            if not text.strip():
                return []
            return [{"kind": "reasoning", "text": text}]
    elif isinstance(msg_chunk, ToolMessage):
        # 工具执行结果：ws_agent 转发为 agent.tool_result，
        # 前端按 toolCallId 回填到对应工具步骤并渲染执行结果
        return [
            {
                "kind": "tool_message",
                "text": item.get("text", ""),
                "tool_call_id": msg_chunk.tool_call_id,
            }
        ]
    return []


def _worker_stream(
    agent, input_payload, config, q: janus.Queue, cancel: threading.Event
):
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
            if isinstance(msg_chunk, AIMessageChunk):
                usage_metadata = msg_chunk.usage_metadata
                if usage_metadata and usage_metadata is not None:
                    q.sync_q.put({"kind": "usage", "usage_metadata": usage_metadata})
            cb = msg_chunk.content_blocks
            if not cb:
                continue
            for item in cb:  # 遍历全部块，避免同帧多块时丢事件
                for event in _extract_item(item, msg_chunk):
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
                        q.sync_q.put(
                            {"kind": "interrupt", "payload": {"actions": interrupts}}
                        )
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
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": _recursion_limit(),
    }
    payload = {"messages": [{"role": "user", "content": user_text}]}
    thread = threading.Thread(
        target=_worker_stream,
        args=(agent, payload, config, q, cancel_event),
        daemon=True,
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


async def resume_turn(
    thread_id: str, decisions: list[dict], cancel_event: threading.Event
):
    """用户对 interrupt 确认后恢复执行（仅对当前仍挂起的 thread 有效）。

    decisions: 决策数组，每个元素为 {"type": "approve"|"reject"|"respond"}，
    数量必须与当前挂起的 interrupt 数量一致。
    "respond" 决策会跳过工具执行，把 message 文本直接作为 ToolMessage 回填
    （见 HITL middleware::_process_decision），可用于把用户新消息带入本轮。
    """
    version, agent = holder.get()
    q = janus.Queue()
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": _recursion_limit(),
    }
    payload = Command(resume={"decisions": decisions})
    thread = threading.Thread(
        target=_worker_stream,
        args=(agent, payload, config, q, cancel_event),
        daemon=True,
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
