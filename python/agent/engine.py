# -*- coding: utf-8 -*-
"""
AgentHolder：按当前配置构建/重建 deep agent 的单例容器。

- checkpointer（sqlite）按 thread_id 持久化，重建图不影响历史会话
- 版本化：进行中的流式回复持有旧实例引用跑完，新一轮消息自动取新实例
"""

import logging
import sqlite3
import threading

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.store.sqlite import SqliteStore


import config_loader
from agent.llms import build_chat_llm
from agent.prompts import build_system_prompt
from agent.tools.builtin_tools import (
    get_date_time,
    internet_search,
    run_command,
    run_python,
    save_user_info,
)
from agent.tools.reminder_tools import (
    create_reminder,
    list_reminders,
    complete_reminder,
    cancel_reminder,
)
from agent.tools.rag_tools import search_from_kb
from agent.constant import DB_URL, WORK_DIR
from agent.middlewares import trim_messages, inject_base_info, inject_kb_info

logger = logging.getLogger(__name__)

# ====================== SQLite 生命周期（连接 + 单例持久层） ======================
# 服务 lifespan 启动时 init_db() 打开、shutdown 时 close_db() 关闭。
#
# 为什么 SqliteSaver / SqliteStore 也必须是进程级单例：
# 两者内部各自用 self.lock 保护对连接的 BEGIN/COMMIT。如果每次 _build()
# 都 new 一套，配置变更重建 agent 后，旧实例仍被进行中的流式回复持有，
# 新旧两个 SqliteStore 共享同一条连接但锁不同，BEGIN/COMMIT 交错即报
# "cannot commit - no transaction is active" 或事务嵌套错误。
# 单例后全部 DB 访问收敛到同一把锁，agent 重建只换 LLM/prompt，不换持久层。
#
# isolation_level=None（autocommit）：SqliteStore 显式执行 BEGIN/COMMIT，
# 默认隐式事务模式会与之冲突（"cannot start a transaction within a transaction"）。
_db_conn: sqlite3.Connection | None = None
_db_saver: SqliteSaver | None = None
_db_store: SqliteStore | None = None
_db_lock = threading.Lock()


def init_db(db_url: str | None = None) -> sqlite3.Connection:
    """打开（或复用）项目级共享 SQLite 连接与持久层单例，幂等。"""
    global _db_conn, _db_saver, _db_store
    with _db_lock:
        if _db_conn is None:
            _db_conn = sqlite3.connect(
                db_url or DB_URL,
                check_same_thread=False,
                isolation_level=None,  # autocommit，见上方说明
            )
            _db_saver = SqliteSaver(_db_conn)
            _db_store = SqliteStore(_db_conn)
            # 共用同一把锁：saver 与 store 的所有 DB 访问全局串行，
            # 杜绝 store 的显式 BEGIN/COMMIT 与 saver 的写入在同一连接上交错
            _db_saver.lock = _db_store.lock
            logger.info("SQLite 共享连接与持久层单例已初始化")
        return _db_conn


def get_checkpointer() -> SqliteSaver:
    """获取共享 checkpointer 单例（惰性初始化）。"""
    init_db()
    assert _db_saver is not None
    return _db_saver


def get_store() -> SqliteStore:
    """获取共享 store 单例（惰性初始化）。"""
    init_db()
    assert _db_store is not None
    return _db_store


def close_db() -> None:
    """关闭共享连接与持久层（服务 shutdown 时调用）。"""
    global _db_conn, _db_saver, _db_store
    with _db_lock:
        if _db_conn is not None:
            try:
                _db_conn.close()
            finally:
                _db_conn = None
                _db_saver = None
                _db_store = None
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
                # run_python,
                save_user_info,
                create_reminder,
                list_reminders,
                complete_reminder,
                cancel_reminder,
                search_from_kb,
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
