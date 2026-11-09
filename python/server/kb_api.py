# -*- coding: utf-8 -*-
"""
知识库 REST API：

- 知识库 CRUD（SQLite 业务记录）
- 文档上传：OCR -> 分块 -> embedding 写入 Chroma（metadata 携带 kb_id / doc_id）
- 文档分块分页查询（供前端信息流滚动加载）
"""

import asyncio
import logging
import os
import time
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from agent.rag.rag_service import get_rag_service
from ocr.ocr_engine import do_ocr
from server.bus import hub
from server.db import kb_repository as kb_repo
from server.protocol import envelope
import paths
import utils

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/kb", tags=["knowledge-base"])

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB，与 OCR 接口保持一致


# ==================== 索引重建任务状态（进程内单任务） ====================
_REBUILD_STATE: dict = {
    "running": False,
    "total": 0,
    "done": 0,
    "failed": 0,
    "current": "",
    "startedAt": None,
    "finishedAt": None,
    "errors": [],
}
_rebuild_task: asyncio.Task | None = None


class KbPayload(BaseModel):
    name: str
    description: Optional[str] = ""


class ChunkUpdatePayload(BaseModel):
    content: str
    metadata: Optional[dict] = None


class KbSearchPayload(BaseModel):
    query: str
    k: int = 8
    hybrid: Optional[bool] = None


# ==================== 知识库 CRUD ====================

@router.get("")
async def list_kbs():
    """列出全部知识库"""
    return {"items": await kb_repo.list_kbs()}


# ==================== 索引健康 / 全量重建 ====================

@router.get("/health")
async def rag_health():
    """索引健康检查：当前 embedding 模型维度 vs 集合维度、分块/文档数与缺失源文件。"""
    rag = get_rag_service()
    info = await asyncio.to_thread(rag.health)
    docs = await kb_repo.list_all_documents()
    missing = [
        d.get("fileName", "")
        for d in docs
        if not d.get("filePath") or not os.path.isfile(d.get("filePath"))
    ]
    info.update({
        "documentCount": len(docs),
        "kbCount": len(await kb_repo.list_kbs()),
        "missingFileCount": len(missing),
        "missingFiles": missing[:8],
        "rebuild": dict(_REBUILD_STATE),
    })
    return info


@router.get("/rebuild/status")
async def rebuild_status():
    """轮询全量重建进度。"""
    return dict(_REBUILD_STATE)


async def _run_rebuild() -> None:
    """按 SQLite 中的原始文件重跑全部 OCR / 分块 / embedding。

    先删除并重建向量集合（清理维度不一致的旧索引），再逐篇回灌；
    缺失源文件的文档标记为 error 并计入 failed，不会阻塞其它文档。
    """
    started_at = _REBUILD_STATE.get("startedAt") or int(time.time() * 1000)
    errors: list[str] = []
    try:
        docs = await kb_repo.list_all_documents()
        _REBUILD_STATE.update(total=len(docs), done=0, failed=0, errors=[])

        rag = get_rag_service()
        await asyncio.to_thread(rag.reset_collection)

        for doc in docs:
            doc_id = doc["id"]
            name = doc.get("fileName") or doc_id
            _REBUILD_STATE["current"] = name
            path = doc.get("filePath") or ""
            try:
                if not path or not os.path.isfile(path):
                    raise FileNotFoundError("原始文件不存在，请重新上传")

                def _read_file() -> bytes:
                    with open(path, "rb") as f:
                        return f.read()

                file_bytes = await asyncio.to_thread(_read_file)
                await kb_repo.set_document_status(doc_id, "processing")

                ocr_result = await do_ocr("rag", name, file_bytes)
                content = (ocr_result or {}).get("page_content", "")
                if not content or not content.strip():
                    raise ValueError("文档解析结果为空")

                metadata = {
                    "kb_id": doc["kbId"],
                    "doc_id": doc_id,
                    "source": name,
                }
                ids = await asyncio.to_thread(rag.save_document, content, metadata)
                if not ids:
                    raise ValueError("文档分块后无有效内容")
                await kb_repo.set_document_status(doc_id, "done", chunk_count=len(ids))
                _REBUILD_STATE["done"] += 1
            except Exception as e:
                logger.warning(f"重建索引领失败: doc={doc_id}, file={name}, err={e}")
                _REBUILD_STATE["failed"] += 1
                errors.append(f"{name}: {e}")
                _REBUILD_STATE["errors"] = errors[:10]
                try:
                    await kb_repo.set_document_status(doc_id, "error", error=str(e))
                except Exception:
                    logger.exception(f"回写文档状态失败: doc={doc_id}")
                # 处理失败也计入进度，前端进度条不会永远停住
                _REBUILD_STATE["done"] += 1
    except Exception as e:
        logger.exception("全量重建索引失败")
        _REBUILD_STATE["failed"] += 1
        errors.append(f"重建失败: {e}")
        _REBUILD_STATE["errors"] = errors[:10]
    finally:
        _REBUILD_STATE["running"] = False
        _REBUILD_STATE["current"] = ""
        _REBUILD_STATE["finishedAt"] = int(time.time() * 1000)
        _REBUILD_STATE["errors"] = errors[:10]
        summary = {
            "status": "success" if _REBUILD_STATE["failed"] == 0 else "partial",
            "total": _REBUILD_STATE["total"],
            "done": _REBUILD_STATE["done"],
            "failed": _REBUILD_STATE["failed"],
            "errors": _REBUILD_STATE["errors"][:5],
            "durationMs": int(time.time() * 1000) - int(started_at),
        }
        try:
            await hub.publish_all(envelope("kb.rebuild.done", summary))
        except Exception:
            logger.exception("广播索引重建结果失败")
        logger.info(
            f"索引重建完成: total={summary['total']}, failed={summary['failed']}"
        )


@router.post("/rebuild")
async def rebuild_index():
    """启动全量索引重建（后台任务）；重复调用时返回当前运行状态。"""
    global _rebuild_task
    if _rebuild_task and not _rebuild_task.done():
        return {"status": "running", **dict(_REBUILD_STATE)}

    # 重建会先清空向量；Embedding 不可用时拒绝启动，避免"删了旧索引又灌不进新索引"
    rag = get_rag_service()
    dim = await asyncio.to_thread(rag._probe_embedding_dim)
    if not dim:
        detail = rag._embedding_error or "Embedding 模型不可用"
        raise HTTPException(status_code=400, detail=f"已取消重建：{detail}")
    _REBUILD_STATE.update({
        "running": True,
        "total": 0,
        "done": 0,
        "failed": 0,
        "current": "",
        "startedAt": int(time.time() * 1000),
        "finishedAt": None,
        "errors": [],
    })
    _rebuild_task = asyncio.create_task(_run_rebuild(), name="kb-rebuild")
    return {"status": "started", **dict(_REBUILD_STATE)}


@router.post("")
async def create_kb(payload: KbPayload):
    """创建知识库"""
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="知识库名称不能为空")
    kb = await kb_repo.create_kb(id=str(uuid4()), name=name, description=payload.description)
    return {"status": "success", "kb": kb}


@router.put("/{kb_id}")
async def update_kb(kb_id: str, payload: KbPayload):
    """更新知识库名称/描述"""
    ok = await kb_repo.update_kb(kb_id, name=payload.name.strip() or None, description=payload.description)
    if not ok:
        raise HTTPException(status_code=404, detail="知识库不存在")
    return {"status": "success"}


@router.delete("/{kb_id}")
async def delete_kb(kb_id: str):
    """删除知识库，并清理其在向量库中的全部分块"""
    ok = await kb_repo.delete_kb(kb_id)
    if not ok:
        raise HTTPException(status_code=404, detail="知识库不存在")
    try:
        count = await asyncio.to_thread(
            get_rag_service().delete_by_metadata, {"kb_id": kb_id}
        )
        logger.info(f"知识库 {kb_id} 向量清理完成，删除 {count} 个分块")
    except Exception:
        logger.exception(f"知识库 {kb_id} 向量清理失败（业务记录已删除）")
    return {"status": "success"}


# ==================== 文档 ====================

@router.get("/{kb_id}/documents")
async def list_documents(kb_id: str):
    """列出知识库下全部文档"""
    if not await kb_repo.get_kb(kb_id):
        raise HTTPException(status_code=404, detail="知识库不存在")
    return {"items": await kb_repo.list_documents(kb_id)}


@router.post("/{kb_id}/documents")
async def upload_document(kb_id: str, file: UploadFile = File(...)):
    """上传文件：OCR -> 分块 -> embedding 入向量库，并登记文档记录"""
    if not await kb_repo.get_kb(kb_id):
        raise HTTPException(status_code=404, detail="知识库不存在")

    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="文件大小超过 20MB 限制")

    filename = file.filename or "unknown"
    ext = os.path.splitext(filename)[1].lower()
    doc_id = str(uuid4())

    # 原始文件落盘到 upload/rag（doc_id 前缀保证唯一并关联文档；basename 防路径穿越）
    rag_upload_dir = os.path.join(paths.data_dir(), "upload", "rag")
    save_path = ""
    try:
        os.makedirs(rag_upload_dir, exist_ok=True)
        safe_name = os.path.basename(filename)
        save_path = os.path.join(rag_upload_dir, f"{doc_id}_{safe_name}")
        await asyncio.to_thread(utils.write_file, save_path, file_bytes)
        logger.info(f"知识库上传文件已保存: {save_path}")
    except OSError:
        save_path = ""
        logger.exception(f"保存知识库上传文件失败: {rag_upload_dir}")

    # 登记文档记录，file_path 落库供后续重新 embedding 使用
    await kb_repo.add_document(
        id=doc_id, kb_id=kb_id, file_name=filename, file_ext=ext,
        file_size=len(file_bytes), file_path=save_path,
    )

    try:
        await kb_repo.set_document_status(doc_id, "processing")

        # OCR 转 markdown
        ocr_result = await do_ocr("rag", filename, file_bytes)
        content = (ocr_result or {}).get("page_content", "")
        if not content or not content.strip():
            raise ValueError("文档解析结果为空，无可入库内容")

        # 分块 + embedding 写入向量库（同步阻塞操作，放线程池）
        metadata = {
            "kb_id": kb_id,
            "doc_id": doc_id,
            "source": filename,
        }
        rag = get_rag_service()
        ids = await asyncio.to_thread(rag.save_document, content, metadata)
        if not ids:
            raise ValueError("文档分块后无有效内容")

        await kb_repo.set_document_status(doc_id, "done", chunk_count=len(ids))
        doc = await kb_repo.get_document(doc_id)
        return {"status": "success", "document": doc}
    except Exception as e:
        logger.exception(f"文档入库失败: kb={kb_id}, file={filename}, err={e}")
        await kb_repo.set_document_status(doc_id, "error", error=str(e))
        raise HTTPException(status_code=500, detail=f"文档处理失败: {e}")


@router.post("/{kb_id}/search")
async def search_kb(kb_id: str, payload: KbSearchPayload):
    """知识库检索测试：返回混合检索（向量 + BM25）命中的分块与相关度。

    供知识库详情页的「检索测试」使用；Agent 侧检索走 agent/tools/rag_tools.py，
    两边共用 RAGService.search_hits，保证测试结果与线上回答的召回一致。
    """
    if not await kb_repo.get_kb(kb_id):
        raise HTTPException(status_code=404, detail="知识库不存在")
    query = (payload.query or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="查询内容不能为空")
    k = max(1, min(int(payload.k or 8), 20))

    try:
        hits = await asyncio.to_thread(
            get_rag_service().search_hits,
            query=query,
            k=k,
            filter={"kb_id": kb_id},
            hybrid=payload.hybrid,
        )
    except Exception as e:
        logger.exception(f"知识库检索失败: kb={kb_id}, query={query!r}")
        raise HTTPException(status_code=500, detail=f"检索失败: {e}")

    items = []
    for hit in hits:
        meta = hit.get("metadata") or {}
        items.append({
            "id": hit.get("id"),
            "docId": meta.get("doc_id", ""),
            "source": meta.get("source", ""),
            "content": hit.get("content", ""),
            "score": hit.get("score", 0),
            "match": hit.get("match", ""),
            "vectorRank": hit.get("vectorRank"),
            "keywordRank": hit.get("keywordRank"),
        })
    return {"query": query, "items": items, "total": len(items)}


@router.post("/{kb_id}/documents/{doc_id}/reindex")
async def reindex_document(kb_id: str, doc_id: str):
    """重新索引单个文档：重读原始文件 -> 重新 OCR/分块/embedding。

    适用场景：上传时 OCR 引擎不可用、解析失败、或修改了 OCR/分块配置后
    想用同一份原始文件重跑，而不必让用户重新上传。
    """
    doc = await kb_repo.get_document(doc_id)
    if not doc or doc["kbId"] != kb_id:
        raise HTTPException(status_code=404, detail="文档不存在")

    file_path = doc.get("filePath") or ""
    if not file_path or not os.path.isfile(file_path):
        raise HTTPException(
            status_code=400, detail="原始文件不存在（可能已被移动或删除），请重新上传"
        )

    await kb_repo.set_document_status(doc_id, "processing")
    rag = get_rag_service()
    try:
        def _read_file() -> bytes:
            with open(file_path, "rb") as f:
                return f.read()

        file_bytes = await asyncio.to_thread(_read_file)
        removed = await asyncio.to_thread(
            rag.delete_by_metadata, {"doc_id": doc_id}
        )
        ocr_result = await do_ocr("rag", doc["fileName"], file_bytes)
        content = (ocr_result or {}).get("page_content", "")
        if not content or not content.strip():
            raise ValueError("文档解析结果为空，无可入库内容")

        metadata = {
            "kb_id": kb_id,
            "doc_id": doc_id,
            "source": doc["fileName"],
        }
        ids = await asyncio.to_thread(rag.save_document, content, metadata)
        if not ids:
            raise ValueError("文档分块后无有效内容")

        await kb_repo.set_document_status(doc_id, "done", chunk_count=len(ids))
        logger.info(
            f"文档重新索引完成: kb={kb_id}, doc={doc_id}, 旧分块={removed}, 新分块={len(ids)}"
        )
        return {
            "status": "success",
            "document": await kb_repo.get_document(doc_id),
            "removedChunks": removed,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"文档重新索引失败: kb={kb_id}, doc={doc_id}, err={e}")
        await kb_repo.set_document_status(doc_id, "error", error=str(e))
        raise HTTPException(status_code=500, detail=f"重新索引失败: {e}")


@router.delete("/{kb_id}/documents/{doc_id}")
async def delete_document(kb_id: str, doc_id: str):
    """删除文档记录，并清理其在向量库中的全部分块"""
    doc = await kb_repo.get_document(doc_id)
    if not doc or doc["kbId"] != kb_id:
        raise HTTPException(status_code=404, detail="文档不存在")
    await kb_repo.delete_document(doc_id)
    try:
        count = await asyncio.to_thread(
            get_rag_service().delete_by_metadata, {"doc_id": doc_id}
        )
        logger.info(f"文档 {doc_id} 向量清理完成，删除 {count} 个分块")
    except Exception:
        logger.exception(f"文档 {doc_id} 向量清理失败（业务记录已删除）")
    return {"status": "success"}


# ==================== 分块分页查询 ====================

@router.get("/{kb_id}/chunks")
async def list_chunks(
    kb_id: str,
    doc_id: Optional[str] = Query(None, description="按文档过滤（可选）"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=200, description="每页分块数量"),
):
    """
    分页查询知识库（或指定文档）的文档分块，供前端信息流滚动加载。

    返回：{"items": [{id, docId, source, content, metadata}], "total": N, "page": p, "pageSize": s}
    """
    if not await kb_repo.get_kb(kb_id):
        raise HTTPException(status_code=404, detail="知识库不存在")

    where = {"kb_id": kb_id}
    if doc_id:
        where = {"$and": [{"kb_id": kb_id}, {"doc_id": doc_id}]}

    rag = get_rag_service()
    offset = (page - 1) * page_size
    docs, total = await asyncio.to_thread(rag.get_chunks_page, where, offset, page_size)
    items = []
    for d in docs:
        meta = d.metadata or {}
        items.append({
            "id": d.id,
            "docId": meta.get("doc_id", ""),
            "source": meta.get("source", ""),
            "content": d.page_content,
            "metadata": meta,
        })
    return {"items": items, "total": total, "page": page, "pageSize": page_size}


# ==================== 分块编辑 / 删除 ====================

async def _get_chunk_belongs_to_kb(chunk_id: str, kb_id: str) -> dict:
    """校验分块属于指定知识库，返回该分块的 metadata；不属于则抛 404"""
    rag = get_rag_service()
    docs = await asyncio.to_thread(rag.get_by_ids, [chunk_id])
    if not docs:
        raise HTTPException(status_code=404, detail="分块不存在")
    meta = docs[0].metadata or {}
    if meta.get("kb_id") != kb_id:
        raise HTTPException(status_code=404, detail="分块不属于该知识库")
    return meta


@router.put("/{kb_id}/chunks/{chunk_id}")
async def update_chunk(kb_id: str, chunk_id: str, payload: ChunkUpdatePayload):
    """编辑分块内容：重新 embedding 后写回向量库"""
    if not await kb_repo.get_kb(kb_id):
        raise HTTPException(status_code=404, detail="知识库不存在")
    content = (payload.content or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="分块内容不能为空")

    try:
        meta = await _get_chunk_belongs_to_kb(chunk_id, kb_id)
        # 保留原有 kb_id / doc_id / source，避免分块脱离所属文档
        meta.update(payload.metadata or {})
        await asyncio.to_thread(
            get_rag_service().update_chunk, chunk_id, content, meta
        )
        logger.info(f"分块 {chunk_id} 已更新")
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"分块更新失败: {e}")
        raise HTTPException(status_code=500, detail=f"分块更新失败: {e}")


@router.delete("/{kb_id}/chunks/{chunk_id}")
async def delete_chunk(kb_id: str, chunk_id: str):
    """删除单个分块（向量一并清理）"""
    if not await kb_repo.get_kb(kb_id):
        raise HTTPException(status_code=404, detail="知识库不存在")
    try:
        await _get_chunk_belongs_to_kb(chunk_id, kb_id)
        await asyncio.to_thread(get_rag_service().delete_by_ids, [chunk_id])
        logger.info(f"分块 {chunk_id} 已删除")
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"分块删除失败: {e}")
        raise HTTPException(status_code=500, detail=f"分块删除失败: {e}")
