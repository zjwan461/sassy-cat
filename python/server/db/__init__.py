"""
消息持久化模块：基于 SQLAlchemy 的消息和附件存储。
"""

from server.db.database import init_db, close_db, get_session
from server.db.models import Message, Attachment, KnowledgeBase, KbDocument
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
    "KnowledgeBase",
    "KbDocument",
    "save_message",
    "save_attachment",
    "get_messages_by_session",
    "count_messages_by_session",
    "update_message",
    "get_message_by_id"
]
