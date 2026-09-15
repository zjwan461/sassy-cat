"""
消息持久化模块：基于 SQLAlchemy 的消息和附件存储。
"""

from server.db.database import init_db, close_db, get_session
from server.db.models import (
    Message,
    Attachment,
    Conversation,
    KnowledgeBase,
    KbDocument,
    SystemMeta,
)
from server.db.seed import run_seeds, DEFAULT_KB_ID
from server.db.message_repository import (
    save_message,
    save_attachment,
    get_messages_by_session,
    count_messages_by_session,
    update_message,
    get_message_by_id
)

__all__ = [
    "init_db",
    "close_db",
    "get_session",
    "Message",
    "Attachment",
    "Conversation",
    "KnowledgeBase",
    "KbDocument",
    "SystemMeta",
    "run_seeds",
    "DEFAULT_KB_ID",
    "save_message",
    "save_attachment",
    "get_messages_by_session",
    "count_messages_by_session",
    "update_message",
    "get_message_by_id"
]
