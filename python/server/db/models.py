# -*- coding: utf-8 -*-
"""
SQLAlchemy 模型定义：messages 和 attachments 表。
"""

from sqlalchemy import (
    Column,
    String,
    Text,
    Integer,
    BigInteger,
    ForeignKey,
    Index,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Message(Base):
    """聊天消息表"""
    __tablename__ = "messages"
    
    id = Column(String, primary_key=True)              # 消息唯一 ID
    session_id = Column(String, nullable=False, index=True)  # 会话 ID，对应 LangChain 的 thread_id
    role = Column(String, nullable=False)              # 'user' | 'assistant' | 'tool' | 'interrupt'
    content = Column(Text)                             # 消息文本内容
    reasoning = Column(Text)                           # AI 思考内容 (仅 assistant)
    tool_calls = Column(Text)                          # 工具调用名称列表 JSON，如 ["search", "run_cmd"] (仅 assistant)
    tool_call_args = Column(Text)                      # 工具调用参数 JSON，如 {"search": {"q": "..."}} (仅 assistant)
    created_at = Column(BigInteger, nullable=False, index=True)  # 创建时间戳 (毫秒)
    interrupt_actions = Column(Text)                   # 中断请求（需要人工审核的工具执行请求）
    interrupt_decisions = Column(Text)                 # 人工审核的工具记录
    tool_call_result = Column(Text)                    # 工具调用结果
    usage_metadata = Column(Text)                      # token 用量 JSON，如 {"input_tokens":..,"output_tokens":..,"total_tokens":..} (仅 assistant)
    # 关系
    attachments = relationship(
        "Attachment",
        back_populates="message",
        cascade="all, delete-orphan"
    )
    
    __table_args__ = (
        Index("idx_messages_session_time", "session_id", "created_at"),
    )


class Attachment(Base):
    """附件表"""
    __tablename__ = "attachments"
    
    id = Column(String, primary_key=True)              # 附件唯一 ID
    message_id = Column(String, ForeignKey("messages.id"), nullable=False, index=True)
    type = Column(String, nullable=False)              # 'image' | 'document'
    file_name = Column(String, nullable=False)         # 文件名
    file_ext = Column(String)                          # 文件后缀 (如 .pdf, .png)
    file_size = Column(Integer)                        # 文件大小 (字节)
    mime_type = Column(String)                         # MIME 类型
    base64_data = Column(Text)                         # 图片的 base64 数据 (仅 image)
    markdown_content = Column(Text)                    # 文档 OCR 后的 markdown (仅 document)
    created_at = Column(BigInteger, nullable=False)    # 创建时间戳 (毫秒)
    
    # 关系
    message = relationship("Message", back_populates="attachments")


class KnowledgeBase(Base):
    """知识库表（业务概念，向量数据存 Chroma，metadata 携带 kb_id）"""
    __tablename__ = "knowledge_bases"
    
    id = Column(String, primary_key=True)              # 知识库唯一 ID
    name = Column(String, nullable=False)              # 知识库名称
    description = Column(Text)                         # 描述
    created_at = Column(BigInteger, nullable=False)    # 创建时间戳 (毫秒)
    updated_at = Column(BigInteger, nullable=False)    # 更新时间戳 (毫秒)
    
    # 关系
    documents = relationship(
        "KbDocument",
        back_populates="kb",
        cascade="all, delete-orphan"
    )


class KbDocument(Base):
    """知识库文档表（记录上传文件及其向量化状态）"""
    __tablename__ = "kb_documents"
    
    id = Column(String, primary_key=True)              # 文档唯一 ID（同时作为向量库 metadata 的 doc_id）
    kb_id = Column(String, ForeignKey("knowledge_bases.id"), nullable=False, index=True)
    file_name = Column(String, nullable=False)         # 原始文件名
    file_ext = Column(String)                          # 文件后缀
    file_size = Column(Integer)                        # 文件大小 (字节)
    status = Column(String, nullable=False, default="pending")  # pending | processing | done | error
    error = Column(Text)                               # 失败原因 (仅 error)
    chunk_count = Column(Integer, default=0)           # 写入向量库的分块数量
    created_at = Column(BigInteger, nullable=False)    # 上传时间戳 (毫秒)
    
    # 关系
    kb = relationship("KnowledgeBase", back_populates="documents")
    
    __table_args__ = (
        Index("idx_kb_documents_kb", "kb_id", "created_at"),
    )
