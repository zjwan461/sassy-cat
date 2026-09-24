# -*- coding: utf-8 -*-
"""
Agent 流式运行器：在 asyncio 事件循环内消费 langgraph agent.astream，
经 asyncio 队列转发为结构化事件（生产者任务 + 主动取消轮询）。

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

from langgraph.types import Command
from langchain.messages import AIMessageChunk, ToolMessage

import config_loader
from agent.engine import holder

try:  # openai 异常类型用于错误分类（缺失时降级为永不匹配的占位类型）
    from openai import APIConnectionError, APITimeoutError
except Exception:  # pragma: no cover
    class APIConnectionError(Exception):  # type: ignore
        pass

    class APITimeoutError(APIConnectionError):  # type: ignore
        pass

logger = logging.getLogger(__name__)


def _recursion_limit() -> int:
    """从运行时配置读取单轮最大递归步数（优先从 active profile 读取，兼容旧顶层 agent 段），非法值回退为 100"""
    cfg = config_loader.current()
    try:
        return max(1, int(cfg.active_agent_config().get("recursionLimit", 100)))
    except (TypeError, ValueError, AttributeError):
        return 100


def classify_error(e: Exception) -> tuple[str, str]:
    """把底层异常翻译成 (code, 面向用户的中文提示)。

    仅用于把技术异常转成可读文案，不参与任何控制/重试决策。
    拿不到 status 时统一落到 unknown，绝不抛出。
    """
    if isinstance(e, (APIConnectionError, APITimeoutError)):
        return "network", "网络异常或超时，请重试"

    status = getattr(e, "status_code", None)
    try:
        body = str(getattr(e, "body", "")) or str(e)
    except Exception:
        body = str(e)

    if status == 400:
        if "DataInspectionFailed" in body:
            return "content_inspection", "请求被平台内容审核拦截，请调整输入后重试"
        return "bad_request", "请求参数有误（可能是上下文过长或格式问题），请重试或检查输入"
    if status == 401:
        return "auth", "API Key 无效或已过期，请到设置中检查"
    if status == 404:
        return "model_not_found", "模型不存在，请检查模型配置"
    if status == 429:
        return "rate_limit", "请求过于频繁，请稍后重试"
    if isinstance(status, int) and status >= 500:
        return "upstream", "上游服务异常，请稍后重试"
    return "unknown", "生成失败，请重试"


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


async def _worker_stream(
    agent, input_payload, config, q: asyncio.Queue, cancel: threading.Event
):
    """在事件循环内运行异步的 agent.astream，事件推入 asyncio 队列 q"""
    final_parts = []
    try:
        async for _ , stream_mode, chunk in agent.astream(
            input_payload,
            config=config,
            stream_mode=["messages", "custom"],
            subgraphs=True,
        ):
            if cancel.is_set():
                logger.info("收到取消信号，终止流")
                break
            if stream_mode == "messages":
                msg_chunk = chunk[0]
                if isinstance(msg_chunk, AIMessageChunk):
                    usage_metadata = msg_chunk.usage_metadata
                    if usage_metadata and usage_metadata is not None:
                        await q.put({"kind": "usage", "usage_metadata": usage_metadata})
                cb = msg_chunk.content_blocks
                if not cb:
                    continue
                for item in cb:  # 遍历全部块，避免同帧多块时丢事件
                    for event in _extract_item(item, msg_chunk):
                        if event["kind"] == "delta":
                            final_parts.append(event["text"])
                        await q.put(event)
            elif stream_mode == "custom":
                # custom 事件来自工具里的 runtime.stream_writer，结构为
                # {"agent": "dsh", "text": "<增量文本>"}；兼容直接写 str 的旧写法
                #
                # 注意：来源标签不能存进 `agent` 变量——它是本函数的 graph 形参，
                # 覆盖后流尾的 agent.aget_state() 会拿到字符串（interrupt 检查失效）
                if isinstance(chunk, dict):
                    agent_label = chunk.get("agent") or "dsh"
                    text = chunk.get("text") or ""
                else:
                    agent_label, text = "dsh", str(chunk)
                # 同时计入本轮全文：done 的 final_text 既用于 chat.completed，
                # 也是 ws_agent 落库的正文，漏掉这段会让显示与历史不一致
                if text:
                    final_parts.append(text)
                await q.put({"kind": "delta", "text": text, "agent": agent_label})

        # 流结束后检查是否停在 interrupt（待确认）
        if not cancel.is_set():
            try:
                state = await agent.aget_state(config)
                if state.next:  # 存在待执行节点 => 被 interrupt 挂起
                    interrupts = []
                    for state_task in state.tasks:
                        for itr in getattr(state_task, "interrupts", []) or []:
                            interrupts.append(getattr(itr, "value", None))
                    if interrupts:
                        await q.put(
                            {"kind": "interrupt", "payload": {"actions": interrupts}}
                        )
                        await q.put({"kind": "done", "text": "".join(final_parts)})
                        return
            except Exception as e:
                logger.warning(f"检查 interrupt 状态失败: {e}")

        await q.put({"kind": "done", "text": "".join(final_parts)})
    except asyncio.CancelledError:
        # 消费端提前结束本轮时取消本任务，直接向上传播，勿转成 error 事件
        raise
    except Exception as e:
        logger.exception("agent.astream 异常")
        code, msg = classify_error(e)
        # raw 仅用于日志/调试，不下发前端；message 为面向用户的友好文案
        await q.put({"kind": "error", "code": code, "message": msg, "raw": str(e)})


async def _drive_stream(agent, input_payload, config, cancel_event: threading.Event):
    """驱动 _worker_stream：生产者任务写入 asyncio 队列，消费端每 0.1s 主动轮询取消信号。

    即便 agent 处于工具执行 / 上游缓冲等无 chunk 阶段，也能在取消后立即结束本轮，
    避免"停止"延迟数秒（与旧线程 + janus 方案保持一致的响应语义）。
    """
    q: asyncio.Queue = asyncio.Queue()
    task = asyncio.create_task(
        _worker_stream(agent, input_payload, config, q, cancel_event)
    )
    try:
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=0.1)
            except asyncio.TimeoutError:
                # 未取到事件且已取消即立即结束本轮；生产者已结束且队列空亦收尾
                if cancel_event.is_set() or task.done():
                    break
                continue
            yield event
            if event["kind"] in ("done", "error"):
                break
    finally:
        # 不再需要生产者输出：取消其任务，停止后台 astream 消费
        if not task.done():
            task.cancel()


async def run_turn(user_text: str, thread_id: str, cancel_event: threading.Event):
    """发起新一轮对话，异步产出事件"""
    version, agent = holder.get()
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": _recursion_limit(),
    }
    payload = {"messages": [{"role": "user", "content": user_text}]}
    async for event in _drive_stream(agent, payload, config, cancel_event):
        yield event


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
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": _recursion_limit(),
    }
    payload = Command(resume={"decisions": decisions})
    async for event in _drive_stream(agent, payload, config, cancel_event):
        yield event


async def retry_turn(thread_id: str, cancel_event: threading.Event):
    """重试上一轮：从当前 checkpoint 续跑，不追加新的用户输入。

    与 run_turn 的唯一区别是 input_payload 传 None —— LangGraph 会从最后一个
    checkpoint 继续执行（重跑上一轮失败/待执行的节点），因此不会产生重复的用户消息。
    仅当线程仍存在待执行节点时有效；调用方需先校验（见 ws_agent._handle_chat_retry）。
    """
    version, agent = holder.get()
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": _recursion_limit(),
    }
    async for event in _drive_stream(agent, None, config, cancel_event):
        yield event
