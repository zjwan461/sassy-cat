# -*- coding: utf-8 -*-
"""
消息和附件的 CRUD 操作。

所有写入操作都是异步的，失败时仅记录日志，不影响主流程。
"""

import json
import logging
from typing import Optional

from sqlalchemy import select, func, update
from sqlalchemy.orm import selectinload

from server.db.database import get_session
from server.db.models import Message, Attachment

logger = logging.getLogger(__name__)


def _load_json(value):
    """JSON 字段解码：空值返回 None，脏数据原样返回，避免整条消息读取失败。"""
    if not value:
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value


def _message_to_dict(msg: Message) -> dict:
    """统一的消息序列化：分页列表与单条查询共用，避免两处字段口径不一致。"""
    return {
        "id": msg.id,
        "sessionId": msg.session_id,
        "role": msg.role,
        "content": msg.content,
        "reasoning": msg.reasoning,
        "toolCalls": _load_json(msg.tool_calls),
        "toolCallArgs": _load_json(msg.tool_call_args),
        "createdAt": msg.created_at,
        # 这三项在库中是 JSON 文本，必须解码成数组/对象再下发；
        # 之前分页接口漏了 json.loads，前端拿到字符串导致中断卡片/工具结果刷新后丢失。
        "interruptActions": _load_json(msg.interrupt_actions),
        "interruptDecisions": _load_json(msg.interrupt_decisions),
        "toolCallResult": _load_json(msg.tool_call_result),
        "usageMetadata": _load_json(msg.usage_metadata),
        "model": msg.model,
        "durationMs": msg.duration_ms,
        "ttftMs": msg.ttft_ms,
        "decodeMs": msg.decode_ms,
        "decodeTokens": msg.decode_tokens,
        "error": msg.error,
        "subagentName": msg.subagent_name,
        "segments": _load_json(msg.segments),
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


async def save_message(
    id: str,
    session_id: str,
    role: str,
    content: Optional[str] = None,
    reasoning: Optional[str] = None,
    tool_calls: Optional[list] = None,
    tool_call_args: Optional[dict] = None,
    created_at: Optional[int] = None,
    interrupt_actions: Optional[list] = None,
    interrupt_decisions: Optional[list] = None,
    tool_call_result: Optional[list] = None,
    usage_metadata: Optional[dict] = None,
    model: Optional[str] = None,
    duration_ms: Optional[int] = None,
    ttft_ms: Optional[int] = None,
    decode_ms: Optional[int] = None,
    decode_tokens: Optional[int] = None,
    error: Optional[str] = None,
    subagent_name: Optional[str] = None,
    segments: Optional[list] = None,
    attachments: Optional[list[dict]] = None,
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
        created_at: 创建时间戳 (毫秒)，默认当前时间
        usage_metadata: token 用量 (仅 assistant)
    
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
                created_at=created_at or int(time.time() * 1000),
                interrupt_actions=json.dumps(interrupt_actions, ensure_ascii=False) if interrupt_actions else None,
                interrupt_decisions=json.dumps(interrupt_decisions, ensure_ascii=False) if interrupt_decisions else None,
                tool_call_result=json.dumps(tool_call_result, ensure_ascii=False) if tool_call_result else None,
                usage_metadata=json.dumps(usage_metadata, ensure_ascii=False) if usage_metadata else None,
                model=model,
                duration_ms=duration_ms,
                ttft_ms=ttft_ms,
                decode_ms=decode_ms,
                decode_tokens=decode_tokens,
                error=error,
                subagent_name=subagent_name,
                segments=json.dumps(segments, ensure_ascii=False) if segments else None,
            )
            session.add(msg)
            # 附件与消息同事务写入：一次用户消息（含多张图片/文档）只提交一次，
            # 避免 N 个附件产生 N 次 commit，也避免消息已入库、附件丢失的半截状态
            for att in attachments or []:
                session.add(Attachment(**att))
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
    interrupt_actions: Optional[list] = None,
    interrupt_decisions: Optional[list] = None,
    tool_call_result: Optional[list] = None,
    usage_metadata: Optional[dict] = None,
    model: Optional[str] = None,
    duration_ms: Optional[int] = None,
    ttft_ms: Optional[int] = None,
    decode_ms: Optional[int] = None,
    decode_tokens: Optional[int] = None,
    error: Optional[str] = None,
    subagent_name: Optional[str] = None,
    segments: Optional[list] = None,
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
        values: dict = {}
        if session_id is not None:
            values["session_id"] = session_id
        if role is not None:
            values["role"] = role
        if content is not None:
            values["content"] = content
        if reasoning is not None:
            values["reasoning"] = reasoning
        if tool_calls is not None:
            values["tool_calls"] = json.dumps(tool_calls, ensure_ascii=False)
        if tool_call_args is not None:
            values["tool_call_args"] = json.dumps(tool_call_args, ensure_ascii=False)
        if interrupt_actions is not None:
            values["interrupt_actions"] = json.dumps(interrupt_actions, ensure_ascii=False)
        if interrupt_decisions is not None:
            values["interrupt_decisions"] = json.dumps(interrupt_decisions, ensure_ascii=False)
        if tool_call_result is not None:
            values["tool_call_result"] = json.dumps(tool_call_result, ensure_ascii=False)
        if usage_metadata is not None:
            values["usage_metadata"] = json.dumps(usage_metadata, ensure_ascii=False)
        if model is not None:
            values["model"] = model
        if duration_ms is not None:
            values["duration_ms"] = duration_ms
        if ttft_ms is not None:
            values["ttft_ms"] = ttft_ms
        if decode_ms is not None:
            values["decode_ms"] = decode_ms
        if decode_tokens is not None:
            values["decode_tokens"] = decode_tokens
        if error is not None:
            values["error"] = error
        if subagent_name is not None:
            values["subagent_name"] = subagent_name
        if segments is not None:
            values["segments"] = json.dumps(segments, ensure_ascii=False)

        if not values:
            return False

        # 单条 UPDATE 完成：不再先 SELECT 再逐字段赋值。
        # 少了读-改-写的中间态，并发写入时不会互相覆盖对方已提交的字段。
        async with get_session() as session:
            result = await session.execute(
                update(Message).where(Message.id == id).values(**values)
            )
            await session.commit()
            if result.rowcount == 0:
                logger.debug(f"消息不存在: id={id}")
                return False
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
            items = [_message_to_dict(msg) for msg in messages]

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
                logger.debug(f"消息不存在: id={msg_id}")
                return None

            return _message_to_dict(msg)
    except Exception as e:
        logger.error(f"查询消息失败: id={msg_id}, error={e}")
        return None