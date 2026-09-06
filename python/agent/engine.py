# -*- coding: utf-8 -*-
"""
AgentHolder：按当前配置构建/重建 deep agent 的单例容器。

- checkpointer（sqlite）按 thread_id 持久化，重建图不影响历史会话
- 版本化：进行中的流式回复持有旧实例引用跑完，新一轮消息自动取新实例
"""

import logging
import sqlite3
import threading

import sqlite3 as _sqlite3  # noqa: F401 (kept for DB connection)
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langgraph.checkpoint.sqlite import SqliteSaver

import config_loader
from agent.llms import build_chat_llm
from agent.prompts import build_system_prompt
from agent.builtin_tools import get_date_time, internet_search, run_command, run_python
from agent.constant import DB_URL, WORK_DIR

logger = logging.getLogger(__name__)


class AgentHolder:
    def __init__(self):
        self._lock = threading.Lock()
        self._version = 0
        self._agent = None

    def _build(self):
        cfg = config_loader.current()
        profile = cfg.active_llm_profile()
        llm = build_chat_llm(profile)
        system_prompt = build_system_prompt(cfg.get("agent.persona", ""))
        agent = create_deep_agent(
            name="SassyCat",
            model=llm,
            skills=["/skills"],
            tools=[get_date_time, internet_search, run_command, run_python],
            interrupt_on={
                "write_file": True,
                "edit_file": True,
                "delete": True,
            },
            backend=FilesystemBackend(root_dir=WORK_DIR, virtual_mode=True),
            checkpointer=SqliteSaver(_sqlite3.connect(DB_URL, check_same_thread=False)),
            system_prompt=system_prompt,
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
