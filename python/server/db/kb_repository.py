# -*- coding: utf-8 -*-
"""
知识库与知识库文档的 CRUD 操作（SQLite 业务层）。

向量数据本体存 Chroma，metadata 携带 kb_id / doc_id；
本模块仅维护业务侧的知识库与文档记录。
"""

import logging
import time
from typing import Optional

from sqlalchemy import select, func, update, delete

from server.db.database import get_session
from server.db.models import KnowledgeBase, KbDocument

logger = logging.getLogger(__name__)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _kb_to_dict(kb: KnowledgeBase) -> dict:
    return {
        "id": kb.id,
        "name": kb.name,
        "description": kb.description or "",
        "createdAt": kb.created_at,
        "updatedAt": kb.updated_at,
    }


def _doc_to_dict(doc: KbDocument) -> dict:
    return {
        "id": doc.id,
        "kbId": doc.kb_id,
        "fileName": doc.file_name,
        "fileExt": doc.file_ext or "",
        "fileSize": doc.file_size or 0,
        "filePath": doc.file_path or "",
        "status": doc.status,
        "error": doc.error or "",
        "chunkCount": doc.chunk_count or 0,
        "createdAt": doc.created_at,
    }


# ==================== 知识库 ====================

async def create_kb(id: str, name: str, description: Optional[str] = None) -> dict:
    """创建知识库，返回其字典表示"""
    now = _now_ms()
    kb = KnowledgeBase(
        id=id,
        name=name,
        description=description or "",
        created_at=now,
        updated_at=now,
    )
    async with get_session() as session:
        session.add(kb)
        await session.commit()
    logger.info(f"知识库已创建: id={id}, name={name}")
    return _kb_to_dict(kb)


async def list_kbs() -> list[dict]:
    """列出全部知识库（附带文档数与分块总数）"""
    async with get_session() as session:
        kb_rows = (await session.execute(
            select(KnowledgeBase).order_by(KnowledgeBase.created_at.desc())
        )).scalars().all()

        if not kb_rows:
            return []

        # 一次聚合查询统计各知识库的文档数与分块数
        stats_rows = (await session.execute(
            select(
                KbDocument.kb_id,
                func.count(KbDocument.id),
                func.coalesce(func.sum(KbDocument.chunk_count), 0),
            ).group_by(KbDocument.kb_id)
        )).all()
        stats = {row[0]: (row[1], row[2]) for row in stats_rows}

        items = []
        for kb in kb_rows:
            d = _kb_to_dict(kb)
            doc_count, chunk_count = stats.get(kb.id, (0, 0))
            d["docCount"] = int(doc_count)
            d["chunkCount"] = int(chunk_count)
            items.append(d)
        return items


async def get_kb(id: str) -> Optional[dict]:
    """按 ID 获取知识库"""
    async with get_session() as session:
        kb = (await session.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == id)
        )).scalar_one_or_none()
        return _kb_to_dict(kb) if kb else None


async def update_kb(id: str, name: Optional[str] = None, description: Optional[str] = None) -> bool:
    """更新知识库名称/描述"""
    values = {"updated_at": _now_ms()}
    if name is not None:
        values["name"] = name
    if description is not None:
        values["description"] = description
    async with get_session() as session:
        result = await session.execute(
            update(KnowledgeBase).where(KnowledgeBase.id == id).values(**values)
        )
        await session.commit()
        return result.rowcount > 0


async def delete_kb(id: str) -> bool:
    """删除知识库及其文档记录（向量数据由调用方按 kb_id 清理）"""
    async with get_session() as session:
        await session.execute(
            delete(KbDocument).where(KbDocument.kb_id == id)
        )
        result = await session.execute(
            delete(KnowledgeBase).where(KnowledgeBase.id == id)
        )
        await session.commit()
        return result.rowcount > 0


# ==================== 知识库文档 ====================

async def add_document(
    id: str,
    kb_id: str,
    file_name: str,
    file_ext: Optional[str] = None,
    file_size: Optional[int] = None,
    file_path: Optional[str] = None,
) -> dict:
    """登记一篇上传文档（status=pending），返回其字典表示"""
    doc = KbDocument(
        id=id,
        kb_id=kb_id,
        file_name=file_name,
        file_ext=file_ext or "",
        file_size=file_size or 0,
        file_path=file_path or "",
        status="pending",
        chunk_count=0,
        created_at=_now_ms(),
    )
    async with get_session() as session:
        session.add(doc)
        await session.execute(
            update(KnowledgeBase)
            .where(KnowledgeBase.id == kb_id)
            .values(updated_at=_now_ms())
        )
        await session.commit()
    return _doc_to_dict(doc)


async def set_document_status(
    doc_id: str,
    status: str,
    error: Optional[str] = None,
    chunk_count: Optional[int] = None,
) -> bool:
    """更新文档处理状态（processing/done/error）"""
    values = {"status": status}
    if error is not None:
        values["error"] = error
    if chunk_count is not None:
        values["chunk_count"] = chunk_count
    async with get_session() as session:
        result = await session.execute(
            update(KbDocument).where(KbDocument.id == doc_id).values(**values)
        )
        await session.commit()
        return result.rowcount > 0


async def list_documents(kb_id: str) -> list[dict]:
    """列出某知识库下全部文档（按上传时间倒序）"""
    async with get_session() as session:
        rows = (await session.execute(
            select(KbDocument)
            .where(KbDocument.kb_id == kb_id)
            .order_by(KbDocument.created_at.desc())
        )).scalars().all()
        return [_doc_to_dict(d) for d in rows]


async def get_document(doc_id: str) -> Optional[dict]:
    """按 ID 获取文档"""
    async with get_session() as session:
        doc = (await session.execute(
            select(KbDocument).where(KbDocument.id == doc_id)
        )).scalar_one_or_none()
        return _doc_to_dict(doc) if doc else None


async def delete_document(doc_id: str) -> Optional[dict]:
    """删除文档记录，返回被删除的文档字典（供调用方清理向量）；不存在返回 None"""
    async with get_session() as session:
        doc = (await session.execute(
            select(KbDocument).where(KbDocument.id == doc_id)
        )).scalar_one_or_none()
        if not doc:
            return None
        data = _doc_to_dict(doc)
        await session.execute(
            delete(KbDocument).where(KbDocument.id == doc_id)
        )
        await session.execute(
            update(KnowledgeBase)
            .where(KnowledgeBase.id == data["kbId"])
            .values(updated_at=_now_ms())
        )
        await session.commit()
        return data
