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
from server import conversations
from server.bus import hub
from server.protocol import envelope

logger = logging.getLogger(__name__)

# 每个 session 的运行态：当前取消事件
_session_cancel: dict[str, threading.Event] = {}

# 当前激活会话对应的房间 id：所有窗口连接都聚集在该房间，
# 切换会话时整房迁移（见 _activate_room），保证多窗口事件同步
_active_room: str | None = None

# delta 帧节流参数
FLUSH_INTERVAL = 0.05   # 50ms
FLUSH_MAX_CHARS = 80    # 或累积 80 字符


async def _send(ws: WebSocket, frame: dict):
    if ws.client_state == WebSocketState.CONNECTED:
        await ws.send_json(frame)


async def _stream_turn(ws, session_id: str, gen, msg_id: str, cancel: threading.Event):
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
                # 先把已积累的 delta 正文 flush，保证 reasoning 帧不插队到正文之前
                await flush()
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
        # 仅当注册的取消事件仍是本轮的才清理：旧轮次结束时可能已有新轮次
        # 注册了自己的事件，无条件 pop 会误删新轮次的取消句柄
        if _session_cancel.get(session_id) is cancel:
            _session_cancel.pop(session_id, None)


async def _pending_interrupt_decisions(session_id: str, content: str):
    """线程若挂起于未确认的 interrupt，生成把新消息带入 resume 的 decisions 数组。

    背景：用户不点确认直接发新消息时，若按普通新输入 stream，LangGraph 会丢弃
    挂起任务，历史里留下带 tool_calls 却无对应 ToolMessage 的悬挂状态，导致
    后续轮次消息错乱；而先自动 reject 再开新轮，会在历史中多出"用户已拒绝"
    的噪音内容，且额外消耗一次模型收尾调用。

    方案：利用 HITL middleware 的 "respond" 决策（见
    langchain/agents/middleware/human_in_the_loop.py::_process_decision）——
    跳过工具执行，把人类文本直接作为 ToolMessage 回填。将用户新消息作为
    respond 内容带入本轮，模型在同一轮内直接回复新消息：无悬挂状态、
    无拒绝噪音、不多耗一轮收尾调用。
    （不用 Command.update 注入 HumanMessage：那会把新消息插在
    AI(tool_calls) 与 ToolMessage 之间，OpenAI 兼容接口会拒绝该消息序列。）

    返回 decisions 数组；线程无挂起（正常发消息）或异常时返回 None，
    调用方回退到普通 run_turn。
    """
    try:
        _, agent = holder.get()
        state = agent.get_state({"configurable": {"thread_id": session_id}})
        if not (state and state.next):
            return None
        # decisions 数量必须与挂起的 action_requests 总数一致（middleware 校验）
        n = 0
        for task in state.tasks:
            for itr in getattr(task, "interrupts", []) or []:
                val = getattr(itr, "value", None) or {}
                if isinstance(val, dict):
                    n += len(val.get("action_requests") or [])
        if n == 0:
            return None
        logger.info(f"session={session_id} 存在 {n} 个未确认中断，新消息以 respond 决策续跑")
        first = f"用户跳过了待确认的操作（工具未执行），并发送了新消息：{content}"
        rest = "用户跳过了该待确认操作，工具未执行。"
        return [{"type": "respond", "message": first}] + [{"type": "respond", "message": rest}] * (n - 1)
    except Exception as e:
        logger.warning(f"检查挂起中断失败（按普通新轮次处理）: {e}")
        return None


async def _handle_chat_send(ws, payload: dict, room_ref: dict | None = None):
    content = (payload.get("content") or "").strip()
    attachments = payload.get("attachments") or []
    msg_id = uuid.uuid4().hex[:12]
    
    # 消息内容校验：文本和附件至少有一个
    if not content and not attachments:
        await _send(ws, envelope("error", {"message": "空消息"}))
        return
    
    # 构造多模态内容（参考 main_agent.py 中的 LangChain 多模态格式）
    user_content = content
    if attachments:
        content_parts = []
        if content:
            content_parts.append({"type": "text", "text": content})
        for att in attachments:
            if att.get("type") == "image":
                # 图片：base64 格式 {"type": "image", "base64": "...", "mime_type": "..."}
                content_parts.append({
                    "type": "image",
                    "base64": att.get("data", ""),
                    "mime_type": att.get("mimeType", "image/png"),
                })
            elif att.get("type") == "text":
                # OCR 结果：作为文本追加
                if att.get("content"):
                    content_parts.append({"type": "text", "text": att["content"]})
        user_content = content_parts if content_parts else content
    
    # 会话以服务端激活项为唯一权威：客户端携带的 sessionId 可能是切换前的过期值
    # （桌宠窗口长期存活，最容易踩到），采信它会把消息写进错误线程
    session_id = conversations.active_id()
    # 房间对齐：连接所在房间与实际会话不一致时迁移，否则本轮 chat.* 事件 fan-out 收不到
    if room_ref is not None and room_ref.get("id") != session_id:
        await hub.leave(room_ref.get("id"), ws)
        await hub.join(session_id, ws)
        room_ref["id"] = session_id

    # 新会话首条消息：截断生成标题并刷新列表（auto_title 仅在真实改名时返回）
    if conversations.auto_title(session_id, content) is not None:
        await hub.publish_all(envelope("conv.list.result", {"items": conversations.list_sorted()}))
    conversations.touch(session_id)
    conversations.touch(session_id)
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

    # 有挂起未确认中断时：以 respond 决策跳过操作并把新消息带入本轮续跑；
    # 否则正常开新轮
    decisions = await _pending_interrupt_decisions(session_id, content)
    if decisions is not None:
        gen = runner.resume_turn(session_id, decisions, cancel)
    else:
        gen = runner.run_turn(user_content, session_id, cancel)
    await _stream_turn(ws, session_id, gen, msg_id, cancel)
    await hub.publish(session_id, envelope("pet.command", {"action": "idle"}))


async def _handle_tool_confirm(ws, payload: dict):
    # 与 chat.send 一致：以服务端激活会话为权威（确认卡必然属于当前激活对话）
    session_id = conversations.active_id()
    msg_id = uuid.uuid4().hex[:12]

    # 校验线程是否仍挂起于 interrupt：正常流程下新消息已在
    # _handle_chat_send 中以 respond 决策续跑并消费掉挂起中断，
    # 此处主要防御多窗口（桌宠/主窗口）确认卡不同步的竞态，
    # 广播 expired 让前端置灰失效。
    try:
        _, agent = holder.get()
        state = agent.get_state({"configurable": {"thread_id": session_id}})
        pending = bool(state and state.next)
    except Exception as e:
        logger.warning(f"resume 前校验挂起状态失败: {e}")
        pending = True  # 校验异常时保守放行，维持旧行为
    if not pending:
        await hub.publish(session_id, envelope("agent.interrupt.expired", {"sessionId": session_id}))
        return

    cancel = threading.Event()
    # 与 chat.send 一致：同一 session 已有进行中的轮次 -> 先取消，避免双流并发写同一 checkpoint
    old = _session_cancel.get(session_id)
    if old:
        old.set()
    _session_cancel[session_id] = cancel
    await hub.publish(session_id, envelope("chat.started", {"msgId": msg_id, "sessionId": session_id}))

    # 新协议：前端直接发送 decisions 数组
    decisions = payload.get("decisions")
    if decisions and isinstance(decisions, list):
        gen = runner.resume_turn(session_id, decisions, cancel)
    else:
        # 兼容旧协议：approved 布尔值
        approved = bool(payload.get("approved"))
        gen = runner.resume_turn(session_id, [{"type": "approve" if approved else "reject"}], cancel)

    await _stream_turn(ws, session_id, gen, msg_id, cancel)


async def _handle_history(ws, payload: dict):
    # 历史请求同样以激活会话为权威，客户端过期 id 不作为数据源
    session_id = conversations.active_id()
    limit = int(payload.get("limit") or 50)
    try:
        _, agent = holder.get()
        state = agent.get_state({"configurable": {"thread_id": session_id}})
        messages = state.values.get("messages", []) if state else []
        items = []
        # 工具结果截断保护：历史里 ToolMessage 可能携带大段输出，仅回填预览
        TOOL_RESULT_MAX = 500

        def _tool_text(content):
            if isinstance(content, str):
                return content
            try:
                return json.dumps(content, ensure_ascii=False)
            except (TypeError, ValueError):
                return str(content)

        for m in list(messages)[-limit:]:
            mtype = getattr(m, "type", None)
            if mtype == "human":
                content = _tool_text(getattr(m, "content", ""))
                if content.strip():
                    items.append({"role": "user", "text": content})
            elif mtype == "ai":
                content = _tool_text(getattr(m, "content", ""))
                # tool_calls 是本轮工具步骤的骨架来源（含 id/name/args dict）
                tool_calls = getattr(m, "tool_calls", None) or []
                # 正文与工具调用任一非空即保留：纯工具调用轮次的 content 为空，
                # 若仍按旧条件跳过会把其携带的 tool_calls 一并丢失
                if not content.strip() and not tool_calls:
                    continue
                item = {"role": "assistant", "text": content}
                # 提取思考模型的 reasoning 内容
                ak = getattr(m, "additional_kwargs", {}) or {}
                reasoning = ak.get("reasoning_content")
                if reasoning and isinstance(reasoning, str) and reasoning.strip():
                    item["reasoning"] = reasoning
                if tool_calls:
                    item["tools"] = [
                        {"toolCallId": tc.get("id"),
                         "name": tc.get("name"),
                         "args": json.dumps(tc.get("args") or {}, ensure_ascii=False),
                         "done": False}
                        for tc in tool_calls
                    ]
                items.append(item)
            elif mtype == "tool":
                # ToolMessage 按 tool_call_id 配对回填到最近一条 assistant 的 tools 骨架
                target = next((it for it in reversed(items)
                               if it.get("role") == "assistant" and "tools" in it), None)
                call_id = getattr(m, "tool_call_id", None)
                entry = None
                if target and call_id:
                    entry = next((t for t in target["tools"] if t.get("toolCallId") == call_id), None)
                if entry is None:
                    # 配对失败兜底（如骨架已被截断窗口切掉）：孤立追加到最近 assistant
                    if target is None:
                        target = {"role": "assistant", "text": "", "tools": []}
                        items.append(target)
                    else:
                        target.setdefault("tools", [])
                    entry = {"toolCallId": call_id, "name": getattr(m, "name", None)}
                    target["tools"].append(entry)
                result = _tool_text(getattr(m, "content", ""))
                entry["done"] = True
                entry["status"] = getattr(m, "status", None) or "success"
                entry["result"] = result[:TOOL_RESULT_MAX] + ("…" if len(result) > TOOL_RESULT_MAX else "")
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


async def _handle_conv(ws, mtype: str, payload: dict, room_ref: dict):
    """conv.* 会话管理消息路由。room_ref 持有本连接的房间 id（可变，支持切换后迁移）。"""
    if mtype == "conv.list":
        await _send(ws, envelope("conv.list.result", {"items": conversations.list_sorted()}))
    elif mtype == "conv.create":
        conv = conversations.create()
        await _activate_room(conv, room_ref)
    elif mtype == "conv.activate":
        conv = conversations.set_active(payload.get("id") or "")
        if conv is None:
            await _send(ws, envelope("error", {"message": f"会话不存在: {payload.get('id')}"}))
            return
        await _activate_room(conv, room_ref)
    elif mtype == "conv.rename":
        conv = conversations.rename(payload.get("id") or "", payload.get("title") or "")
        if conv is None:
            await _send(ws, envelope("error", {"message": f"会话不存在: {payload.get('id')}"}))
            return
        await hub.publish_all(envelope("conv.list.result", {"items": conversations.list_sorted()}))
    elif mtype == "conv.delete":
        cid = payload.get("id") or ""
        removed = conversations.delete(cid)
        if not removed:
            await _send(ws, envelope("error", {"message": f"会话不存在: {cid}"}))
            return
        # 删除的是激活会话：active_id() 已自动回退，广播让所有窗口跟随切换
        await hub.publish_all(envelope("conv.list.result", {"items": conversations.list_sorted()}))
        active = conversations.get(conversations.active_id())
        if active:
            await _activate_room(active, room_ref)


async def _activate_room(conv: dict, room_ref: dict):
    """激活会话变更：整房迁移 + 全局广播，桌宠/多窗口无需重连即跟随切换。"""
    global _active_room
    old = _active_room
    if old and old != conv["id"]:
        await hub.move_room(old, conv["id"])
    _active_room = conv["id"]
    room_ref["id"] = conv["id"]
    await hub.publish_all(envelope("conv.activated", {"id": conv["id"], "title": conv.get("title", "")}))


async def ws_agent_endpoint(ws: WebSocket):
    await ws.accept()
    client = ws.query_params.get("client", "main")
    # 一律加入"当前激活会话"房间（服务端为权威）：客户端 query 里的 sessionId 可能是
    # 切换前的过期值，采信它会让连接落入无人认领的房间、收不到 chat.* 广播
    session_id = conversations.active_id()
    room_ref = {"id": session_id}  # 可变引用：conv.activate 后房间随之迁移
    if client != "system":
        await hub.join(session_id, ws)
        global _active_room
        if _active_room is None:
            _active_room = session_id
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
                    asyncio.create_task(_handle_chat_send(ws, payload, room_ref))
                elif mtype == "chat.cancel":
                    sid = payload.get("sessionId") or room_ref.get("id") or "default"
                    ev = _session_cancel.get(sid)
                    if ev:
                        ev.set()
                    await hub.publish(sid, envelope("pet.command", {"action": "idle"}))
                elif mtype == "tool.confirm":
                    asyncio.create_task(_handle_tool_confirm(ws, payload))
                elif mtype == "chat.history":
                    await _handle_history(ws, payload)
                elif mtype.startswith("conv."):
                    await _handle_conv(ws, mtype, payload, room_ref)
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
        # 房间可能已随会话切换迁移（room_ref），以最新房间 id 退出
        await hub.leave(room_ref.get("id") or session_id, ws)
        logger.info(f"WS 连接关闭 client={client} session={room_ref.get('id') or session_id}")
