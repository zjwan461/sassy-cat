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


def _get_harness():
    """惰性创建并复用 dsh runtime（连接参数全部来自 config.user.json）。"""
    global _HARNESS
    if _HARNESS is None:
        settings = dsh_invoker.load_llm_settings(dsh_invoker.resolve_config_path())
        _HARNESS = dsh_invoker.build_harness(settings)
    return _HARNESS


def _drop_harness() -> None:
    """丢弃当前实例：子进程异常退出后，下次调用重建一个干净的。"""
    global _HARNESS
    harness, _HARNESS = _HARNESS, None
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
    分块（text-chunks），按原顺序回放即可让前端继续渲染打字动画。
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
    """
    writer = runtime.stream_writer

    thread_id = ""
    config = getattr(runtime, "config", None) or {}
    configurable = config.get("configurable") or {}
    if configurable.get("thread_id"):
        thread_id = str(configurable["thread_id"])

    loop = asyncio.get_running_loop()
    # 工作线程 -> 事件循环的单向通道：on_notification 只投递，不直接碰 writer
    queue: asyncio.Queue = asyncio.Queue()

    # 只把根会话的正文写出去：subagent 子会话的事件不该串进这条回复
    root_session: dict = {"id": None}

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
            # 正文回放 text-chunks（纯工具调用步骤没有 text-chunks，此处为空）
            chunks: list[str] = []
            reasoning = _format_reasoning(event)
            if reasoning:
                chunks.append(reasoning)
            chunks.extend(_iter_assistant_text(event))
            pieces: Iterator[str] = iter(chunks)
        elif etype == "tool/call":
            # dsh 调用工具：工具名 + 参数，渲染成引用块 markdown 混入正文流
            pieces = iter([_format_tool_call(event)])
        elif etype == "tool/result":
            # dsh 工具执行结果：同样以引用块 markdown 追加
            pieces = iter([_format_tool_result(event)])
        else:
            return
        for piece in pieces:
            loop.call_soon_threadsafe(queue.put_nowait, piece)

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

    return result.final_response or "deepseek harness job finished"
