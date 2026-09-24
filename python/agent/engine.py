# -*- coding: utf-8 -*-
"""
AgentHolder：按当前配置构建/重建 deep agent 的单例容器。

- checkpointer（sqlite）按 thread_id 持久化，重建图不影响历史会话
- 版本化：进行中的流式回复持有旧实例引用跑完，新一轮消息自动取新实例
"""

import logging
import threading

import aiosqlite
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.store.sqlite.aio import AsyncSqliteStore


import config_loader
from agent.llms import build_chat_llm
from agent.prompts import build_system_prompt
from agent.tools.builtin_tools import (
    create_skill,
    get_date_time,
    internet_search,
    run_command,
    save_user_info,
)
from agent.tools.reminder_tools import (
    create_reminder,
    list_reminders,
    complete_reminder,
    cancel_reminder,
)
from agent.tools.rag_tools import search_from_kb
from agent.tools.subagent_tool import call_dsh
from agent.constant import DB_URL, WORK_DIR
from agent.middlewares import trim_messages, inject_base_info, inject_kb_info

logger = logging.getLogger(__name__)

# ====================== SQLite 生命周期（异步连接 + 单例持久层） ======================
# 服务 lifespan 启动时 await init_db() 打开、shutdown 时 await close_db() 关闭。
#
# 为什么用 AsyncSqliteSaver / AsyncSqliteStore：
# agent 现经 agent.astream 在事件循环内执行，LangGraph 的异步执行循环会直接
# await checkpointer.aget_tuple/aput/aput_writes 与 store.abatch。同步版
# SqliteSaver / SqliteStore 的异步方法会抛 NotImplementedError，故必须换成异步实现。
#
# 为什么 saver / store 仍共用同一条连接 + 同一把锁：
# AsyncSqliteSaver 与 AsyncSqliteStore 各自在事务里显式 BEGIN/COMMIT。若二者
# 共用一条 aiosqlite 连接却各持一把锁，BEGIN/COMMIT 会交错，报
# "cannot commit - no transaction is active" 或事务嵌套错误。单例 + 复用 saver
# 的锁后全部 DB 事务串行化，agent 重建只换 LLM/prompt，不换持久层。
#
# isolation_level=None（autocommit）：AsyncSqliteStore 显式执行 BEGIN/COMMIT，
# 默认隐式事务模式会与之冲突（"cannot start a transaction within a transaction"）。
_db_conn: aiosqlite.Connection | None = None
_db_saver: AsyncSqliteSaver | None = None
_db_store: AsyncSqliteStore | None = None
_db_lock = threading.Lock()


async def init_db(db_url: str | None = None) -> aiosqlite.Connection:
    """打开（或复用）项目级共享 SQLite 异步连接与持久层单例，幂等。

    必须在运行中的事件循环内 await —— AsyncSqliteSaver / AsyncSqliteStore 依赖
    get_running_loop 绑定自身的事件循环与锁，无法在同步上下文（线程外）构建。
    """
    global _db_conn, _db_saver, _db_store
    if _db_conn is not None:
        return _db_conn
    conn = await aiosqlite.connect(
        db_url or DB_URL,
        isolation_level=None,  # autocommit，见上方说明
    )
    saver = AsyncSqliteSaver(conn)
    store = AsyncSqliteStore(conn)
    # 复用同一把锁：saver 与 store 的所有 DB 事务全局串行，
    # 杜绝 store 的显式 BEGIN/COMMIT 与 saver 的写入在同一连接上交错
    store.lock = saver.lock
    await saver.setup()
    await store.setup()
    with _db_lock:
        _db_conn, _db_saver, _db_store = conn, saver, store
    logger.info("SQLite 共享异步连接与持久层单例已初始化")
    return conn


def get_checkpointer() -> AsyncSqliteSaver:
    """获取共享 checkpointer 单例（须先 await init_db()）。"""
    if _db_saver is None:
        raise RuntimeError("agent 持久层未初始化：请先 await agent.engine.init_db()")
    return _db_saver


def get_store() -> AsyncSqliteStore:
    """获取共享 store 单例（须先 await init_db()）。"""
    if _db_store is None:
        raise RuntimeError("agent 持久层未初始化：请先 await agent.engine.init_db()")
    return _db_store


async def close_db() -> None:
    """关闭共享连接与持久层（服务 shutdown 时调用）。"""
    global _db_conn, _db_saver, _db_store
    with _db_lock:
        conn = _db_conn
        _db_conn = None
        _db_saver = None
        _db_store = None
    if conn is not None:
        await conn.close()
        logger.info("SQLite 共享连接已关闭")


class AgentHolder:
    def __init__(self):
        self._lock = threading.Lock()
        self._version = 0
        self._agent = None

    def _build(self):
        cfg = config_loader.current()
        profile = cfg.active_llm_profile()
        llm = build_chat_llm(profile)
        system_prompt = build_system_prompt(cfg.active_agent_config().get("persona", ""))
        # 高危工具人工确认策略（agent.interruptOn，可在设置页配置）：
        # true = 执行前打断等待用户确认；false = 直接放行
        interrupt_on = cfg.get("agent.interruptOn") or {}
        # 共享持久层单例：未显式 init_db 时惰性初始化（如 CLI 调试入口）
        agent = create_deep_agent(
            name="SassyCat",
            model=llm,
            skills=["/skills"],
            tools=[
                get_date_time,
                internet_search,
                run_command,
                save_user_info,
                create_skill,
                create_reminder,
                list_reminders,
                complete_reminder,
                cancel_reminder,
                search_from_kb,
                call_dsh,
            ],
            interrupt_on=interrupt_on,
            backend=FilesystemBackend(root_dir=WORK_DIR, virtual_mode=True),
            checkpointer=get_checkpointer(),
            system_prompt=system_prompt,
            store=get_store(),
            # 注意顺序：inject_kb_info 必须在 inject_base_info 之后，
            # 否则 base info 的标记剥离逻辑会丢掉知识库段落
            middleware=[trim_messages, inject_base_info, inject_kb_info],
        )
        return agent

    def get(self):
        """返回 (version, agent)，惰性构建"""
        with self._lock:
            if self._agent is None:
                self._agent = self._build()
                self._version += 1
                logger.info(f"Agent 已构建 (version={self._version})")
            return self._version, self._agent

    def invalidate(self):
        """配置变更后调用：强制下一轮重建"""
        with self._lock:
            self._agent = None
            logger.info("Agent 配置已失效，将在下一轮对话重建")


holder = AgentHolder()
