from langchain.tools import tool, ToolRuntime
import logging
import re
import threading
import uuid
from typing import Any, Iterator

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
    """把一条 assistant/message 事件拆成可增量拼接的文本块。

    dsh 的会话事件是"结算式"的：整块消息一次到达，但 data.stream 里保留了原始
    分块（text-chunks），按原顺序回放即可让前端继续渲染打字动画。
    reasoning 块不写出去：前端的思考内容走 agent.reasoning 通道，混进正文会污染回复。
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

    # writer({"agent": "dsh", "text": "dsh start handle"})

    thread_id = ""
    config = getattr(runtime, "config", None) or {}
    configurable = config.get("configurable") or {}
    if configurable.get("thread_id"):
        thread_id = str(configurable["thread_id"])

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
        event = payload.get("event") or {}
        if event.get("type") != "assistant/message":
            return
        for piece in _iter_assistant_text(event):
            writer({"agent": "dsh", "text": piece})

    session_id = _session_id_for(thread_id)

    try:
        with _HARNESS_LOCK:
            harness = _get_harness()
            try:
                result = harness.run(
                    prompt,
                    session_id=session_id,
                    on_notification=on_notification,
                )
            except JsonRpcError as exc:
                if "already exists" not in str(exc):
                    _drop_harness()
                    raise
                # 同名会话是上一次进程留下的：换一个新 id 重试一次
                session_id = _fork_session_id(thread_id)
                root_session["id"] = None
                result = harness.run(
                    prompt,
                    session_id=session_id,
                    on_notification=on_notification,
                )
            except Exception:
                _drop_harness()
                raise
    except Exception as exc:
        logger.exception("dsh 委托执行失败")
        writer({"agent": "dsh", "text": f"dsh error: {exc}"})
        return f"dsh 执行失败: {exc}"

    # writer({"agent": "dsh", "text": "dsh finish handle"})
    return result.final_response or "deepseek harness job finished"
