import asyncio
import json
from langchain.tools import tool, ToolRuntime
import logging
import re
import threading
import uuid
from typing import Any, Callable, Iterator

# 兼容两种入口：以 python/ 为根（main.py 注入 sys.path）或项目根为根
try:
    from agent.tools.dsh import dsh_invoker
except ImportError:  # pragma: no cover - 取决于启动方式
    from python.agent.tools.dsh import dsh_invoker

try:
    from deepseek_harness.errors import JsonRpcError
except ImportError:  # pragma: no cover - dsh 不可用时不该阻断模块导入
    JsonRpcError = Exception  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)

# harness 启动要拉起 node 子进程并加载 dsh profile，每次调用都重建会多花几秒，
# 所以整个进程复用同一个实例；会话粒度见下面的 _THREAD_SESSIONS。
_HARNESS_LOCK = threading.RLock()
_HARNESS: Any = None

# langchain thread_id -> 本进程正在使用的 dsh session id
_SESSION_LOCK = threading.RLock()
_THREAD_SESSIONS: dict[str, str] = {}


# 配置变更后置脏标记：下次委托时重建 harness。此处不直接 close，避免与正在执行的
# harness.run 抢 _HARNESS_LOCK（_run_blocking 持锁期间可能正在跑一轮长任务）。
_HARNESS_STALE = False


def invalidate_harness() -> None:
    """配置变更后调用（见 server/ws_agent.py 的 config.invalidate 分支）。

    只置脏标记、不关停实例：真正的重建推迟到下一次 call_dsh，在 _HARNESS_LOCK
    内完成，既保证配置热生效（无需重启服务），又不会打断进行中的委托。
    """
    global _HARNESS_STALE
    _HARNESS_STALE = True


def _get_harness():
    """惰性创建并复用 dsh runtime（连接参数全部来自 config.user.json）。

    不变量：必须在 _HARNESS_LOCK 内调用（唯一调用点 _run_blocking 已持锁），
    否则 _drop_harness() 的 close 可能打断正在执行的一轮。
    """
    global _HARNESS, _HARNESS_STALE
    if _HARNESS is None or _HARNESS_STALE:
        if _HARNESS is not None:
            _drop_harness()
        settings = dsh_invoker.load_llm_settings(dsh_invoker.resolve_config_path())
        _HARNESS = dsh_invoker.build_harness(settings)
        _HARNESS_STALE = False
    return _HARNESS


def _drop_harness() -> None:
    """丢弃当前实例：子进程异常退出 / 配置变更后，下次调用重建一个干净的。"""
    global _HARNESS, _HARNESS_STALE
    harness, _HARNESS = _HARNESS, None
    _HARNESS_STALE = False
    if harness is not None:
        try:
            harness.close()
        except Exception:
            logger.warning("关闭 dsh harness 失败", exc_info=True)


def _sanitize_thread_id(thread_id: str) -> str:
    """dsh 拿 sessionId 当目录名，先清洗成文件名安全字符。"""
    safe = re.sub(r"[^0-9A-Za-z._-]", "-", thread_id or "").strip("-")
    return (safe or "sassy-thread")[:80]


def _session_id_for(thread_id: str) -> str:
    """把 langchain 的 thread_id 映射成 dsh 的 session id。

    同一 thread_id 在本进程内复用同一个 dsh 会话，于是跨调用有连续上下文
    （dsh 允许在同一会话上继续排队新消息）；换会话即换 thread_id。
    """
    safe = _sanitize_thread_id(thread_id)
    with _SESSION_LOCK:
        return _THREAD_SESSIONS.setdefault(safe, safe)


def _fork_session_id(thread_id: str) -> str:
    """上一个进程留下的同名会话无法 attach（SDK 协议没有 resume），换新 id 继续。"""
    safe = _sanitize_thread_id(thread_id)
    forked = f"{safe}-{uuid.uuid4().hex[:8]}"
    with _SESSION_LOCK:
        _THREAD_SESSIONS[safe] = forked
    logger.warning("dsh 会话 %s 已存在于磁盘（上次运行遗留），改用 %s", safe, forked)
    return forked


def _iter_assistant_text(event: dict) -> Iterator[str]:
    """把一条 assistant/message 事件拆成可增量拼接的正文文本块。

    dsh 的会话事件是"结算式"的：整块消息一次到达，但 data.stream 里保留了原始
    分块（text-chunks），按原顺序回放即可拼回完整正文。
    思考内容（reasoning-chunks）不在这里产出，另行经 _format_reasoning 渲染成引用块。
    """
    data = event.get("data") or {}

    replayed = False
    for entry in data.get("stream") or []:
        if not isinstance(entry, dict) or entry.get("type") != "text-chunks":
            continue
        for piece in entry.get("texts") or []:
            if isinstance(piece, str) and piece:
                replayed = True
                yield piece
    if replayed:
        return

    # 事件被压缩/裁剪后没有可回放的分块时，退回最终消息的整段文本
    message = data.get("message") or {}
    for block in message.get("content") or []:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text") or ""
            if text:
                yield text


# 工具结果正文超过该字数就截断，避免 dsh 的 shell / 文件输出把回复正文淹没
_TOOL_RESULT_MAX_CHARS = 500


def _blockquote(text: str) -> str:
    """把一段文本整段包进 markdown 引用块（每行都加 "> " 前缀）。

    引用块里的围栏代码块要求每一行都处于 "> " 之下，否则代码块会脱出引用块、
    退化成普通段落。空行写成裸 ">" 以保持引用块连续。
    """
    return "\n".join(("> " + ln) if ln else ">" for ln in text.split("\n"))


def _format_tool_call(event: dict) -> str:
    """把一条 tool/call 事件渲染成引用块 markdown（工具名 + 完整参数）。"""
    data = event.get("data") or {}
    name = data.get("name") or "tool"
    raw_args = data.get("arguments") or ""
    # 参数是 JSON 字符串：能解析就缩进美化，否则原样透出
    try:
        args = json.dumps(json.loads(raw_args), ensure_ascii=False, indent=2)
    except (ValueError, TypeError):
        args = str(raw_args)
    body = f"🛠️ 调用工具 `{name}`\n```json\n{args}\n```"
    return _blockquote(body) + "\n\n"


def _extract_tool_result(message: dict) -> tuple[str, bool]:
    """从 tool/result 的 message 里取出正文文本与是否出错标记。"""
    texts: list[str] = []
    is_error = False
    for block in message.get("content") or []:
        if not isinstance(block, dict) or block.get("type") != "tool-result":
            continue
        if block.get("isError"):
            is_error = True
        for inner in block.get("content") or []:
            if isinstance(inner, dict) and inner.get("type") == "text":
                text = inner.get("text") or ""
                if text:
                    texts.append(text)
    return "\n".join(texts), is_error


def _format_tool_result(event: dict) -> str:
    """把一条 tool/result 事件渲染成引用块 markdown（结果，超长截断）。"""
    data = event.get("data") or {}
    text, is_error = _extract_tool_result(data.get("message") or {})
    text = text.strip("\n") or "（无输出）"
    if len(text) > _TOOL_RESULT_MAX_CHARS:
        omitted = len(text) - _TOOL_RESULT_MAX_CHARS
        text = text[:_TOOL_RESULT_MAX_CHARS] + f"\n…（省略 {omitted} 字）"
    icon = "❌" if is_error else "✅"
    body = f"{icon} 结果\n```text\n{text}\n```"
    return _blockquote(body) + "\n\n"


def _assistant_reasoning_text(event: dict) -> str:
    """取出 assistant/message 里的深度思考内容（reasoning-chunks 按序拼接）。

    与正文同样是"结算式"的：原始分块留在 data.stream 的 reasoning-chunks 里。
    事件被压缩/裁剪后无分块时，退回 message.content 里的 reasoning 块。
    """
    data = event.get("data") or {}

    text = ""
    for entry in data.get("stream") or []:
        if not isinstance(entry, dict) or entry.get("type") != "reasoning-chunks":
            continue
        for piece in entry.get("texts") or []:
            if isinstance(piece, str):
                text += piece
    if text:
        return text

    message = data.get("message") or {}
    for block in message.get("content") or []:
        if isinstance(block, dict) and block.get("type") == "reasoning":
            piece = block.get("reasoning") or block.get("text") or ""
            if piece:
                text += piece
    return text


def _format_reasoning(event: dict) -> str | None:
    """把 dsh 的深度思考渲染成引用块 markdown（全文，不截断）；无内容返回 None。"""
    text = _assistant_reasoning_text(event).strip("\n")
    if not text:
        return None
    # 引用块内出现 ``` 会开启围栏，一旦不闭合会把后续内容吞进代码块；
    # 转义掉连续 3 个及以上的反引号，避免破坏外层结构（单个/成对反引号保留行内代码）
    text = re.sub(r"`{3,}", lambda m: "\\`" * len(m.group(0)), text)
    return _blockquote(f"💭 深度思考\n{text}") + "\n\n"


# todo 清单状态用 unicode 符号表示：markdown-it 没挂 task-list 插件，
# "- [x] ..." 会原样显示成文本，符号则渲染稳定
_TODO_MARKS = {
    "completed": "☑",
    "in_progress": "▶",
    "pending": "☐",
}


def _format_todos(event: dict, previous: str) -> tuple[str, str]:
    """把一条 todo/write 快照渲染成引用块里的任务清单，返回 (文本, 新指纹)。

    todo/write 是**全量快照**而非增量：dsh 每结束一步就重发整份清单（实测一轮
    4 次，且每次状态都变）。清单与上次相同时返回空文本让调用方跳过，避免把
    同一份清单在正文里刷很多遍。
    """
    todos = (event.get("data") or {}).get("todos")
    if not isinstance(todos, list) or not todos:
        return "", previous

    fingerprint = json.dumps(todos, ensure_ascii=False, sort_keys=True)
    if fingerprint == previous:
        return "", previous

    lines: list[str] = []
    done = 0
    for item in todos:
        if not isinstance(item, dict):
            continue
        if item.get("status") == "completed":
            done += 1
        mark = _TODO_MARKS.get(item.get("status"), "☐")
        content = str(item.get("content") or "").strip() or "(未命名)"
        lines.append(f"- {mark} {content}")

    body = f"📋 待办（{done}/{len(todos)} 完成）\n" + "\n".join(lines)
    return _blockquote(body) + "\n\n", fingerprint


def _format_compaction(event: dict) -> str | None:
    """把 compaction/* 事件压成一行提示；没有信息量的阶段返回 None。

    长任务里 dsh 会把旧历史总结/裁剪掉，这行能解释"它怎么突然记不住前面了"。
    """
    data = event.get("data") or {}
    etype = event.get("type")

    if etype == "compaction/summary":
        count = len(data.get("shadowedSeqs") or [])
        tokens = data.get("shadowedTokenCount")
        detail = f"{count} 条 / 约 {tokens} tokens" if tokens else f"{count} 条"
        return _blockquote(f"🗜️ 已压缩历史：{detail}") + "\n\n"
    if etype == "compaction/prune":
        count = len(data.get("shadowedSeqs") or [])
        return _blockquote(f"🗜️ 已裁剪历史：{count} 条") + "\n\n"
    if etype == "compaction/end":
        error = data.get("error")
        # 成功时上面 summary 已经交代过，不必再来一行；只有失败才补一条
        if error:
            return _blockquote(f"🗜️ 上下文压缩失败：{error}") + "\n\n"
        return None
    # compaction/start 单独出现没有信息量
    return None


def _result_error_detail(result: Any) -> str:
    """从 RunResult.events 里抽取 dsh 轮次失败的原因文本。

    dsh 的 turn/end 事件在失败时形如
    {data: {reason: {kind: "error", error: {message, code}}}}；
    个别引擎只在 assistant/attempt 的 stream.chunk.finish.failure 里带失败详情。
    两种都兜一下，拿不到则返回空串。
    """
    for event in reversed(getattr(result, "events", None) or []):
        etype = event.get("type")
        data = event.get("data") or {}
        if etype == "turn/end":
            reason = data.get("reason") or {}
            err = reason.get("error") or {}
            detail = err.get("message") or err.get("code")
            if detail:
                return str(detail)
        elif etype == "assistant/attempt":
            for entry in data.get("stream") or []:
                if not isinstance(entry, dict):
                    continue
                chunk = entry.get("chunk")
                finish = chunk.get("finish") if isinstance(chunk, dict) else None
                reason = finish.get("reason") if isinstance(finish, dict) else None
                failure = reason.get("failure") if isinstance(reason, dict) else None
                if isinstance(failure, dict):
                    detail = failure.get("message") or failure.get("code")
                    if detail:
                        return str(detail)
    return ""


def _presented_files(result: Any) -> list[str]:
    """收集本轮 present 声明交付的文件路径（去重保序）。

    dsh 只在模型显式调用 present 时才发 deliverables/presented；当一轮没有助手正文、
    却确实产出了文件时，用它兜底给出可见的结果，避免退化成"无内容"。
    """
    files: list[str] = []
    seen: set[str] = set()
    for event in getattr(result, "events", None) or []:
        if event.get("type") != "deliverables/presented":
            continue
        for item in (event.get("data") or {}).get("files") or []:
            path = item.get("path") if isinstance(item, dict) else None
            if path and path not in seen:
                seen.add(path)
                files.append(str(path))
    return files


def _run_blocking(
    prompt: str,
    thread_id: str,
    on_notification: Callable[[Any], None],
    root_session: dict,
):
    """在工作线程里执行 harness.run（换线程以免阻塞事件循环）。

    harness.run 是同步阻塞的：直接调用会占住事件循环，导致 custom 增量与整个
    服务的收发都被冻住直到整轮结束。放到线程后，on_notification 在工作线程里
    触发，由调用方桥接回循环再写出。

    同名会话残留（上次进程遗留）时换新 id 重试一次；其余异常丢弃 harness，
    以便下次调用重建一个干净的实例。
    """
    session_id = _session_id_for(thread_id)
    with _HARNESS_LOCK:
        harness = _get_harness()
        try:
            return harness.run(
                prompt, session_id=session_id, on_notification=on_notification
            )
        except JsonRpcError as exc:
            if "already exists" not in str(exc):
                _drop_harness()
                raise
            # 同名会话是上一次进程留下的：换一个新 id 重试一次
            session_id = _fork_session_id(thread_id)
            root_session["id"] = None
            return harness.run(
                prompt, session_id=session_id, on_notification=on_notification
            )
        except Exception:
            _drop_harness()
            raise


@tool
async def call_dsh(prompt: str, runtime: ToolRuntime) -> str:
    """把任务委托给 deepseek harness（dsh）执行，并把执行过程与结果流式返回。

    dsh 是一套独立的 agent 运行时（自带 shell / str_replace_editor / present
    工具与持久会话），适合多步、需要反复读写文件的子任务。请给出完整自包含的
    任务描述，因为它看不到当前对话的上下文。

    会话按 langchain 的 thread_id 归属：同一会话里多次委托会复用同一个 dsh 会话，
    因此它可以记住前几次委托的内容。
    注意：stream_writer 写出的结构是 {"agent": "dsh", "text": "..."}，
    runner 的 custom 分支会从里面取 text 作为正文增量、agent 作为来源标记。
    各类内容都按事件到达顺序整块写出，不做逐字延迟（无打字机效果）。
    """
    writer = runtime.stream_writer

    thread_id = ""
    config = getattr(runtime, "config", None) or {}
    configurable = config.get("configurable") or {}
    if configurable.get("thread_id"):
        thread_id = str(configurable["thread_id"])

    loop = asyncio.get_running_loop()
    # 工作线程 -> 事件循环的单向通道：on_notification 只投递，不直接碰 writer。
    # 队列元素就是要写出的文本片段。
    queue: asyncio.Queue = asyncio.Queue()

    def push(text: str) -> None:
        """把一段文本交给事件循环侧写出（本函数在工作线程里被调用）。"""
        loop.call_soon_threadsafe(queue.put_nowait, text)

    # 只把根会话的正文写出去：subagent 子会话的事件不该串进这条回复
    root_session: dict = {"id": None}
    # 上一份 todo 快照的指纹（todo/write 是全量重发，靠它去重）
    todo_state: dict = {"fingerprint": ""}

    def on_notification(notification: Any) -> None:
        if notification.method != "session.event":
            return
        payload = notification.payload or {}
        session_id = payload.get("sessionId")
        if root_session["id"] is None:
            root_session["id"] = session_id
        if session_id != root_session["id"]:
            return
        # 本回调在工作线程执行：runtime.stream_writer 内部要走 get_config()，
        # 而 contextvar 不跨线程，直接调用会抛 "Called get_config outside of a
        # runnable context"。这里只把片段投递回事件循环，由循环侧写出。
        event = payload.get("event") or {}
        etype = event.get("type")
        if etype == "assistant/message":
            # 思考内容先于正文（与生成顺序一致），同样以引用块 markdown 混入正文流；
            # 正文回放 text-chunks（纯工具调用步骤没有 text-chunks，此处为空）。
            reasoning = _format_reasoning(event)
            if reasoning:
                push(reasoning)
            for piece in _iter_assistant_text(event):
                push(piece)
            return
        if etype == "tool/call":
            # dsh 调用工具：工具名 + 参数，渲染成引用块 markdown 混入正文流
            push(_format_tool_call(event))
            return
        if etype == "tool/result":
            # dsh 工具执行结果：同样以引用块 markdown 追加
            push(_format_tool_result(event))
            return
        if etype == "todo/write":
            # 待办清单：全量快照，清单没变时（返回空文本）直接跳过
            text, todo_state["fingerprint"] = _format_todos(
                event, todo_state["fingerprint"]
            )
            if text:
                push(text)
            return
        if etype.startswith("compaction/"):
            # 上下文压缩：只在有信息量的阶段输出一行
            piece = _format_compaction(event)
            if piece:
                push(piece)
            return

    # 换线程执行阻塞的 harness.run；同时在事件循环上把队列里的片段实时写出
    run_task = asyncio.create_task(
        asyncio.to_thread(
            _run_blocking, prompt, thread_id, on_notification, root_session
        )
    )
    # 提前挂 done 回调：异常/取消时也取走异常，避免 "exception never retrieved" 警告
    run_task.add_done_callback(
        lambda t: None if t.cancelled() else t.exception()
    )

    try:
        while not run_task.done():
            try:
                piece = await asyncio.wait_for(queue.get(), timeout=0.1)
            except asyncio.TimeoutError:
                continue
            writer({"agent": "dsh", "text": piece})
        # 线程已结束：冲刷队列尾部残余（最后几段的投递回调可能刚执行完）
        while True:
            try:
                piece = queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            writer({"agent": "dsh", "text": piece})
        result = run_task.result()
    except Exception as exc:
        logger.exception("dsh 委托执行失败")
        writer({"agent": "dsh", "text": f"dsh error: {exc}"})
        return f"dsh 执行失败: {exc}"

    # final_response 是 SDK 给出的"本轮最后一条助手正文"。为空时绝不能回落到一句
    # 假完成占位串——那会把"轮次失败"伪装成"已完成"，主 agent 据此就会谎报结果。
    # 实网故障即如此：模型网关 TRANSPORT 失败、自动重试耗尽，一个 token 都没产出，
    # turn/end 的 reason.kind == "error"，final_response 为空 → 曾返回
    # "deepseek harness job finished"。因此这里按 finish_reason 如实区分。
    final = result.final_response
    if final:
        return final

    reason = result.finish_reason
    if reason == "error":
        detail = _result_error_detail(result) or "未知错误"
        logger.warning("dsh 轮次失败（未产出正文）: %s", detail)
        writer({"agent": "dsh", "text": f"\n\n❌ dsh 执行失败：{detail}\n\n"})
        return f"dsh 执行失败（未产出结果）：{detail}"

    if reason == "max-tokens":
        msg = "dsh 达到输出上限被截断，未产出完整结果，请缩小任务范围后重试"
        writer({"agent": "dsh", "text": f"\n\n⚠️ {msg}\n\n"})
        return msg

    files = _presented_files(result)
    if files:
        listing = "\n".join(f"- {path}" for path in files)
        return f"dsh 未返回文本正文，但已交付以下文件：\n{listing}"

    msg = f"dsh 未返回任何文本内容（finish_reason={reason or 'none'}）"
    writer({"agent": "dsh", "text": f"\n\n⚠️ {msg}\n\n"})
    return msg
