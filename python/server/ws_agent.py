# -*- coding: utf-8 -*-
"""
/ws/agent WebSocket 端点：聊天调度、房间 fan-out、控制帧处理。

连接参数：?client=pet|main|system&sessionId=xxx
 - client=system：Electron 主进程活动信号通道，不加入聊天房间
"""

import asyncio
import json
import logging
import threading
import time
import uuid

from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

import config_loader
from agent import runner
from agent.engine import holder
from agent.prompts import build_system_prompt, DEFAULT_PERSONA
from proactive import scheduler
from server.bus import hub
from server.protocol import envelope

logger = logging.getLogger(__name__)

# 每个 session 的运行态：当前取消事件
_session_cancel: dict[str, threading.Event] = {}

# delta 帧节流参数
FLUSH_INTERVAL = 0.05   # 50ms
FLUSH_MAX_CHARS = 80    # 或累积 80 字符


async def _send(ws: WebSocket, frame: dict):
    if ws.client_state == WebSocketState.CONNECTED:
        await ws.send_json(frame)


async def _stream_turn(ws, session_id: str, gen, msg_id: str):
    """消费 runner 事件生成器，节流后 fan-out 到房间"""

    async def emit(evt_type: str, payload: dict):
        await hub.publish(session_id, envelope(evt_type, payload), exclude=None)

    buffer = []
    args_buffer = []
    last_flush = time.monotonic()

    async def flush():
        nonlocal buffer, args_buffer, last_flush
        if buffer:
            await emit("chat.delta", {"msgId": msg_id, "text": "".join(buffer)})
            buffer = []
        if args_buffer:
            # 工具参数增量合并发送（节流，避免高频小帧）
            await emit("agent.tool_args", {"msgId": msg_id, "args": "".join(args_buffer)})
            args_buffer = []
        last_flush = time.monotonic()

    try:
        async for event in gen:
            kind = event["kind"]
            if kind == "delta":
                buffer.append(event["text"])
                if (time.monotonic() - last_flush >= FLUSH_INTERVAL
                        or sum(len(x) for x in buffer) >= FLUSH_MAX_CHARS):
                    await flush()
            elif kind == "tool_args":
                args_buffer.append(event["args"])
                if (time.monotonic() - last_flush >= FLUSH_INTERVAL
                        or sum(len(x) for x in args_buffer) >= FLUSH_MAX_CHARS):
                    await flush()
            elif kind == "reasoning":
                await emit("agent.reasoning", {"msgId": msg_id, "text": event.get("text", "")})
            elif kind == "tool":
                await flush()
                await emit("agent.tool_call", {
                    "msgId": msg_id, "name": event.get("name"),
                    "phase": event.get("phase"),
                })
            elif kind == "interrupt":
                await flush()
                await emit("agent.interrupt", {
                    "msgId": msg_id,
                    "callId": uuid.uuid4().hex[:8],
                    "actions": event["payload"].get("actions"),
                })
            elif kind == "done":
                await flush()
                await emit("chat.completed", {"msgId": msg_id, "text": event.get("text", "")})
            elif kind == "error":
                await flush()
                await emit("chat.error", {"msgId": msg_id, "code": "agent_error",
                                           "message": event.get("message", "")})
    except Exception as e:
        logger.exception("stream turn 异常")
        await emit("chat.error", {"msgId": msg_id, "code": "internal", "message": str(e)})
    finally:
        _session_cancel.pop(session_id, None)


async def _handle_chat_send(ws, payload: dict):
    session_id = payload.get("sessionId") or "default"
    content = (payload.get("content") or "").strip()
    msg_id = uuid.uuid4().hex[:12]
    if not content:
        await _send(ws, envelope("error", {"message": "空消息"}))
        return

    cancel = threading.Event()
    # 同一 session 已有进行中的轮次 -> 先取消
    old = _session_cancel.get(session_id)
    if old:
        old.set()
    _session_cancel[session_id] = cancel

    # 用户消息回显给房间内所有连接（携带 source 标记，供多窗口同步显示）
    # 注意：chat.user 使用独立的 user_msg_id，避免与助手回复的 msg_id 冲突
    # （否则接收端 find(msgId) 会把 delta 追加到用户气泡上）
    user_msg_id = "u-" + msg_id
    await hub.publish(session_id, envelope("chat.user", {
        "msgId": user_msg_id, "sessionId": session_id, "content": content, "source": ws.query_params.get("client", "main"),
    }))
    await hub.publish(session_id, envelope("chat.started", {"msgId": msg_id, "sessionId": session_id}))
    await hub.publish(session_id, envelope("pet.command", {"action": "think"}))

    gen = runner.run_turn(content, session_id, cancel)
    await _stream_turn(ws, session_id, gen, msg_id)
    await hub.publish(session_id, envelope("pet.command", {"action": "idle"}))


async def _handle_tool_confirm(ws, payload: dict):
    session_id = payload.get("sessionId") or "default"
    approved = bool(payload.get("approved"))
    msg_id = uuid.uuid4().hex[:12]
    cancel = threading.Event()
    _session_cancel[session_id] = cancel
    await hub.publish(session_id, envelope("chat.started", {"msgId": msg_id, "sessionId": session_id}))
    gen = runner.resume_turn(session_id, approved, cancel)
    await _stream_turn(ws, session_id, gen, msg_id)


async def _handle_history(ws, payload: dict):
    session_id = payload.get("sessionId") or "default"
    limit = int(payload.get("limit") or 50)
    try:
        _, agent = holder.get()
        state = agent.get_state({"configurable": {"thread_id": session_id}})
        messages = state.values.get("messages", []) if state else []
        items = []
        for m in list(messages)[-limit:]:
            mtype = getattr(m, "type", None)
            if mtype in ("human", "ai") and getattr(m, "content", None):
                content = m.content if isinstance(m.content, str) else json.dumps(m.content, ensure_ascii=False)
                if content.strip():
                    item = {"role": "user" if mtype == "human" else "assistant",
                            "text": content}
                    # 提取思考模型的 reasoning 内容
                    if mtype == "ai":
                        ak = getattr(m, "additional_kwargs", {}) or {}
                        reasoning = ak.get("reasoning_content")
                        if reasoning and isinstance(reasoning, str) and reasoning.strip():
                            item["reasoning"] = reasoning
                    items.append(item)
        await _send(ws, envelope("chat.history.result", {"sessionId": session_id, "items": items}))
    except Exception as e:
        logger.warning(f"读取历史失败: {e}")
        await _send(ws, envelope("chat.history.result", {"sessionId": session_id, "items": [], "error": str(e)}))


async def _handle_llm_test(ws, payload: dict):
    cfg = config_loader.current()
    profile = cfg.active_llm_profile()
    try:
        from agent.llms import build_chat_llm
        llm = build_chat_llm(profile)
        start = time.time()
        resp = await asyncio.wait_for(llm.ainvoke("回复：OK"), timeout=15)
        latency = int((time.time() - start) * 1000)
        await _send(ws, envelope("llm.test.result", {
            "ok": True, "latencyMs": latency,
            "reply": str(getattr(resp, "content", ""))[:80],
        }))
    except Exception as e:
        await _send(ws, envelope("llm.test.result", {"ok": False, "error": str(e)}))


async def ws_agent_endpoint(ws: WebSocket):
    await ws.accept()
    client = ws.query_params.get("client", "main")
    session_id = ws.query_params.get("sessionId") or None
    if client != "system" and session_id:
        await hub.join(session_id, ws)
    logger.info(f"WS 连接建立 client={client} session={session_id}")
    try:
        await _send(ws, envelope("connected", {"client": client, "sessionId": session_id}))
        while True:
            raw = await ws.receive_text()
            try:
                frame = json.loads(raw)
            except json.JSONDecodeError:
                await _send(ws, envelope("error", {"message": "非 JSON 帧"}))
                continue
            mtype = frame.get("type")
            payload = frame.get("payload") or {}
            # 任何来自客户端的帧都视为用户活动信号（重置闲置计时）
            scheduler.state.ping()
            try:
                if mtype == "ping":
                    await _send(ws, envelope("pong", {}))
                elif mtype == "chat.send":
                    asyncio.create_task(_handle_chat_send(ws, payload))
                elif mtype == "chat.cancel":
                    sid = payload.get("sessionId") or session_id or "default"
                    ev = _session_cancel.get(sid)
                    if ev:
                        ev.set()
                    await hub.publish(sid, envelope("pet.command", {"action": "idle"}))
                elif mtype == "tool.confirm":
                    asyncio.create_task(_handle_tool_confirm(ws, payload))
                elif mtype == "chat.history":
                    await _handle_history(ws, payload)
                elif mtype == "prompt.preview":
                    final = build_system_prompt(payload.get("persona") or DEFAULT_PERSONA)
                    await _send(ws, envelope("prompt.preview.result", {"prompt": final}))
                elif mtype == "llm.test":
                    await _handle_llm_test(ws, payload)
                elif mtype == "config.invalidate":
                    config_loader.reload_config()
                    holder.invalidate()
                    await _send(ws, envelope("config.invalidated", {"paths": payload.get("paths", [])}))
                elif mtype == "client.event":
                    name = payload.get("name")
                    if name == "user_activity":
                        ev = payload.get("event")
                        if ev == "lock-screen":
                            scheduler.state.lock()
                        elif ev == "unlock-screen":
                            scheduler.state.unlock()
                        else:
                            scheduler.state.ping()
                else:
                    await _send(ws, envelope("error", {"message": f"未知类型: {mtype}"}))
            except Exception as e:
                logger.exception("帧处理异常")
                await _send(ws, envelope("error", {"message": str(e)}))
    except WebSocketDisconnect:
        pass
    finally:
        await hub.leave(session_id, ws)
        logger.info(f"WS 连接关闭 client={client} session={session_id}")
