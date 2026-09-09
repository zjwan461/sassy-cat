# -*- coding: utf-8 -*-
"""
消息和附件的 CRUD 操作。

所有写入操作都是异步的，失败时仅记录日志，不影响主流程。
"""

import json
import logging
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from server.db.database import get_session
from server.db.models import Message, Attachment

logger = logging.getLogger(__name__)


async def save_message(
    id: str,
    session_id: str,
    role: str,
    content: Optional[str] = None,
    reasoning: Optional[str] = None,
    tool_calls: Optional[list] = None,
    tool_call_args: Optional[dict] = None,
    tool_call_id: Optional[str] = None,
    tool_name: Optional[str] = None,
    tool_status: Optional[str] = None,
    created_at: Optional[int] = None,
    interrupt_actions: Optional[list] = None,
    interrupt_decisions: Optional[list] = None,
) -> bool:
    """
    保存消息到数据库。
    
    Args:
        id: 消息唯一 ID
        session_id: 会话 ID（对应 LangChain thread_id）
        role: 消息类型 ('user' | 'assistant' | 'tool')
        content: 消息文本内容
        reasoning: AI 思考内容 (仅 assistant)
        tool_calls: 工具调用名称列表 (仅 assistant)
        tool_call_args: 工具调用参数映射 (仅 assistant)
        tool_call_id: 工具结果关联 ID (仅 tool)
        tool_name: 工具名称 (仅 tool)
        tool_status: 工具执行状态 (仅 tool)
        created_at: 创建时间戳 (毫秒)，默认当前时间
    
    Returns:
        bool: 是否保存成功
    """
    import time
    
    try:
        async with get_session() as session:
            msg = Message(
                id=id,
                session_id=session_id,
                role=role,
                content=content,
                reasoning=reasoning,
                tool_calls=json.dumps(tool_calls, ensure_ascii=False) if tool_calls else None,
                tool_call_args=json.dumps(tool_call_args, ensure_ascii=False) if tool_call_args else None,
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                tool_status=tool_status,
                created_at=created_at or int(time.time() * 1000),
                interrupt_actions=json.dumps(interrupt_actions, ensure_ascii=False) if interrupt_actions else None,
                interrupt_decisions=json.dumps(interrupt_decisions, ensure_ascii=False) if interrupt_decisions else None,
            )
            session.add(msg)
            await session.commit()
            logger.debug(f"消息已保存: id={id}, role={role}")
            return True
    except Exception as e:
        logger.warning(f"保存消息失败 (不影响聊天): id={id}, error={e}")
        return False


async def update_message(
    id: str,
    session_id: Optional[str] = None,
    role: Optional[str] = None,
    content: Optional[str] = None,
    reasoning: Optional[str] = None,
    tool_calls: Optional[list] = None,
    tool_call_args: Optional[dict] = None,
    tool_call_id: Optional[str] = None,
    tool_name: Optional[str] = None,
    tool_status: Optional[str] = None,
    interrupt_actions: Optional[list] = None,
    interrupt_decisions: Optional[list] = None,
) -> bool:
    """
    更新消息到数据库。
    
    Args:
        id: 消息唯一 ID（用于定位要更新的消息）
        session_id: 会话 ID
        role: 消息类型 ('user' | 'assistant' | 'tool')
        content: 消息文本内容
        reasoning: AI 思考内容 (仅 assistant)
        tool_calls: 工具调用名称列表 (仅 assistant)
        tool_call_args: 工具调用参数映射 (仅 assistant)
        tool_call_id: 工具结果关联 ID (仅 tool)
        tool_name: 工具名称 (仅 tool)
        tool_status: 工具执行状态 (仅 tool)
        interrupt_actions: 中断请求列表
        interrupt_decisions: 中断决定列表
    
    Returns:
        bool: 是否更新成功
    """
    try:
        async with get_session() as session:
            # 查询消息
            stmt = select(Message).where(Message.id == id)
            result = await session.execute(stmt)
            msg = result.scalar_one_or_none()
            
            if msg is None:
                logger.warning(f"消息不存在: id={id}")
                return False
            
            # 更新提供的字段
            if session_id is not None:
                msg.session_id = session_id
            if role is not None:
                msg.role = role
            if content is not None:
                msg.content = content
            if reasoning is not None:
                msg.reasoning = reasoning
            if tool_calls is not None:
                msg.tool_calls = json.dumps(tool_calls, ensure_ascii=False)
            if tool_call_args is not None:
                msg.tool_call_args = json.dumps(tool_call_args, ensure_ascii=False)
            if tool_call_id is not None:
                msg.tool_call_id = tool_call_id
            if tool_name is not None:
                msg.tool_name = tool_name
            if tool_status is not None:
                msg.tool_status = tool_status
            if interrupt_actions is not None:
                msg.interrupt_actions = json.dumps(interrupt_actions, ensure_ascii=False)
            if interrupt_decisions is not None:
                msg.interrupt_decisions = json.dumps(interrupt_decisions, ensure_ascii=False)
            
            await session.commit()
            logger.debug(f"消息已更新: id={id}")
            return True
    except Exception as e:
        logger.warning(f"更新消息失败 (不影响聊天): id={id}, error={e}")
        return False


async def save_attachment(
    id: str,
    message_id: str,
    type: str,
    file_name: str,
    file_ext: Optional[str] = None,
    file_size: Optional[int] = None,
    mime_type: Optional[str] = None,
    base64_data: Optional[str] = None,
    markdown_content: Optional[str] = None,
    created_at: Optional[int] = None,
) -> bool:
    """
    保存附件到数据库。
    
    Args:
        id: 附件唯一 ID
        message_id: 关联的消息 ID
        type: 附件类型 ('image' | 'document')
        file_name: 文件名
        file_ext: 文件后缀
        file_size: 文件大小 (字节)
        mime_type: MIME 类型
        base64_data: 图片的 base64 数据 (仅 image)
        markdown_content: 文档 OCR 后的 markdown (仅 document)
        created_at: 创建时间戳 (毫秒)
    
    Returns:
        bool: 是否保存成功
    """
    import time
    
    try:
        async with get_session() as session:
            att = Attachment(
                id=id,
                message_id=message_id,
                type=type,
                file_name=file_name,
                file_ext=file_ext,
                file_size=file_size,
                mime_type=mime_type,
                base64_data=base64_data,
                markdown_content=markdown_content,
                created_at=created_at or int(time.time() * 1000),
            )
            session.add(att)
            await session.commit()
            logger.debug(f"附件已保存: id={id}, type={type}")
            return True
    except Exception as e:
        logger.warning(f"保存附件失败 (不影响聊天): id={id}, error={e}")
        return False


async def get_messages_by_session(
    session_id: str,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict], int]:
    """
    分页查询会话消息（含附件）。
    
    Args:
        session_id: 会话 ID
        page: 页码（从 1 开始）
        page_size: 每页数量
    
    Returns:
        tuple: (消息列表, 总数)
    """
    try:
        async with get_session() as session:
            # 先查询总数
            count_stmt = select(func.count()).select_from(Message).where(Message.session_id == session_id)
            count_result = await session.execute(count_stmt)
            total = count_result.scalar() or 0
            
            # 查询消息（含附件）
            offset = (page - 1) * page_size
            stmt = (
                select(Message)
                .where(Message.session_id == session_id)
                .options(selectinload(Message.attachments))
                .order_by(Message.created_at.desc())
                .offset(offset)
                .limit(page_size)
            )
            
            result = await session.execute(stmt)
            messages = result.scalars().all()
            
            # 转换为字典列表
            items = []
            for msg in messages:
                item = {
                    "id": msg.id,
                    "sessionId": msg.session_id,
                    "role": msg.role,
                    "content": msg.content,
                    "reasoning": msg.reasoning,
                    "toolCalls": json.loads(msg.tool_calls) if msg.tool_calls else None,
                    "toolCallArgs": json.loads(msg.tool_call_args) if msg.tool_call_args else None,
                    "toolCallId": msg.tool_call_id,
                    "toolName": msg.tool_name,
                    "toolStatus": msg.tool_status,
                    "createdAt": msg.created_at,
                    "interruptActions": msg.interrupt_actions,
                    "interruptDecisions": msg.interrupt_decisions,
                    "attachments": [
                        {
                            "id": att.id,
                            "type": att.type,
                            "fileName": att.file_name,
                            "fileExt": att.file_ext,
                            "fileSize": att.file_size,
                            "mimeType": att.mime_type,
                            "base64Data": att.base64_data,
                            "markdownContent": att.markdown_content,
                        }
                        for att in msg.attachments
                    ],
                }
                items.append(item)
            
            return items, total
    except Exception as e:
        logger.error(f"查询消息失败: session_id={session_id}, error={e}")
        return [], 0


async def count_messages_by_session(session_id: str) -> int:
    """
    统计会话消息数量。
    
    Args:
        session_id: 会话 ID
    
    Returns:
        int: 消息数量
    """
    try:
        async with get_session() as session:
            stmt = select(func.count()).select_from(Message).where(Message.session_id == session_id)
            result = await session.execute(stmt)
            return result.scalar() or 0
    except Exception as e:
        logger.error(f"统计消息数量失败: session_id={session_id}, error={e}")
        return 0

async def get_message_by_id(msg_id: str) -> Optional[dict]:
    """
    根据 message_id 查询消息数据（含附件）。

    Args:
        msg_id: 消息唯一 ID

    Returns:
        Optional[dict]: 消息字典（含附件），不存在时返回 None
    """
    try:
        async with get_session() as session:
            stmt = (
                select(Message)
                .where(Message.id == msg_id)
                .options(selectinload(Message.attachments))
            )
            result = await session.execute(stmt)
            msg = result.scalar_one_or_none()

            if msg is None:
                logger.warning(f"消息不存在: id={msg_id}")
                return None

            return {
                "id": msg.id,
                "sessionId": msg.session_id,
                "role": msg.role,
                "content": msg.content,
                "reasoning": msg.reasoning,
                "toolCalls": json.loads(msg.tool_calls) if msg.tool_calls else None,
                "toolCallArgs": json.loads(msg.tool_call_args) if msg.tool_call_args else None,
                "toolCallId": msg.tool_call_id,
                "toolName": msg.tool_name,
                "toolStatus": msg.tool_status,
                "createdAt": msg.created_at,
                "interruptActions": json.loads(msg.interrupt_actions) if msg.interrupt_actions else None,
                "interruptDecisions": json.loads(msg.interrupt_decisions) if msg.interrupt_decisions else None,
                "attachments": [
                    {
                        "id": att.id,
                        "type": att.type,
                        "fileName": att.file_name,
                        "fileExt": att.file_ext,
                        "fileSize": att.file_size,
                        "mimeType": att.mime_type,
                        "base64Data": att.base64_data,
                        "markdownContent": att.markdown_content,
                    }
                    for att in msg.attachments
                ],
            }
    except Exception as e:
        logger.error(f"查询消息失败: id={msg_id}, error={e}")
        return None