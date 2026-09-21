# -*- coding: utf-8 -*-
"""
FastAPI 应用：lifespan 内运行 proactive 调度与 reminder 后台任务。
"""

import asyncio
import logging
import os
import time

from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from agent import engine as agent_engine
from agent.rag import model_download
from agent.rag.rag_service import get_rag_service
from ocr.ocr_engine import do_ocr
from proactive import reminder_runner, scheduler
from server.ws_agent import ws_agent_endpoint
from server.kb_api import router as kb_router
from server.stats_api import router as stats_router
from server.skills_api import router as skills_router
from server.db import init_db as init_message_db, close_db as close_message_db
from server.db import get_messages_by_session, DEFAULT_KB_ID
from server.db import kb_repository as kb_repo
from uuid import uuid4
import paths
import utils

logger = logging.getLogger(__name__)

# RAG 本地嵌入模型下载：同一时刻仅允许一个下载任务
_rag_download_busy = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 打开 agent 共享 SQLite 连接（checkpointer/store 复用，shutdown 时统一关闭）
    await asyncio.to_thread(agent_engine.init_db)
    # 初始化消息数据库（SQLAlchemy 异步引擎）
    await init_message_db()
    stop_event = asyncio.Event()
    proactive_task = asyncio.create_task(scheduler.run_forever(stop_event))
    reminder_task = asyncio.create_task(reminder_runner.run_forever(stop_event))
    logger.info("后台任务已启动：proactive_scheduler / reminder_runner")
    yield
    stop_event.set()
    proactive_task.cancel()
    reminder_task.cancel()
    await asyncio.gather(proactive_task, reminder_task, return_exceptions=True)
    await asyncio.to_thread(agent_engine.close_db)
    await close_message_db()
    logger.info("后台任务已停止")


def create_app() -> FastAPI:
    app = FastAPI(title="sassy-cat-agent", lifespan=lifespan)
    # 渲染进程（file:// 或 localhost:5173）直连 WS；WS 不受 CORS 约束，HTTP 侧宽松即可
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health():
        return {"ok": True, "ts": int(time.time() * 1000)}

    @app.post("/api/ocr")
    async def ocr_endpoint(file: UploadFile = File(...)):
        """文档 OCR：接收文件，返回 markdown 文本"""
        chat_upload_dir = paths.data_dir() + "/upload/chat"
        MAX_SIZE = 20 * 1024 * 1024  # 20MB
        file_bytes = await file.read()
        if len(file_bytes) > MAX_SIZE:
            raise HTTPException(status_code=413, detail="文件大小超过 20MB 限制")
        # 将收到的文件落盘到 chat 上传目录（文件名做 basename 防路径穿越，重名时加时间戳）
        save_path = ""  # 落盘失败时为空串，文档记录仍会登记（向量化失败标 error）
        try:
            os.makedirs(chat_upload_dir, exist_ok=True)
            safe_name = os.path.basename(file.filename or "unknown")
            save_path = os.path.join(chat_upload_dir, safe_name)
            if os.path.exists(save_path):
                stem, ext = os.path.splitext(safe_name)
                save_path = os.path.join(chat_upload_dir, f"{stem}_{int(time.time() * 1000)}{ext}")
            await asyncio.to_thread(utils.write_file, save_path, file_bytes)
            logger.info(f"上传文件已保存: {save_path}")
        except OSError:
            logger.exception(f"保存上传文件失败: {chat_upload_dir}")
        try:
            result = await do_ocr("chat", file.filename or "unknown", file_bytes)
            markdown = result.get("page_content", "")
            # 异步后台保存到 default 知识库（OCR 内容自动向量化，供 RAG 检索），不阻塞 OCR 响应
            asyncio.create_task(save_to_default_kb(
                content=markdown,
                file_name=file.filename or "unknown",
                file_path=save_path,
                file_ext=os.path.splitext(file.filename or "")[1].lower(),
                file_size=len(file_bytes),
            ))
            return {
                "status": "success",
                "filename": file.filename,
                "markdown": markdown,
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"OCR 处理失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def save_to_default_kb(content: str, file_name: str, file_path: str, file_ext: str, file_size: int):
        """将聊天中上传的非图片文件异步保存到 default 知识库（OCR 内容自动向量化，供 RAG 检索）"""
        try:
            content = (content or "").strip()
            if not content:
                logger.warning(f"聊天文件 OCR 内容为空，跳过默认知识库保存: {file_name}")
                return

            # 1. 登记文档记录（status=pending），file_path 落库供后续重新向量化使用
            doc_id = str(uuid4())
            await kb_repo.add_document(
                id=doc_id,
                kb_id=DEFAULT_KB_ID,
                file_name=file_name,
                file_ext=file_ext,
                file_size=file_size,
                file_path=file_path,
            )

            # 2. 分块 + embedding 写入向量库（同步阻塞操作放线程池），metadata 携带 kb_id/doc_id
            await kb_repo.set_document_status(doc_id, "processing")
            metadata = {
                "kb_id": DEFAULT_KB_ID,
                "doc_id": doc_id,
                "source": file_name,
            }
            rag = get_rag_service()
            ids = await asyncio.to_thread(rag.save_document, content, metadata)
            if not ids:
                raise ValueError("文档分块后无有效内容")

            # 3. 更新文档状态，与知识库文档上传流程保持一致
            await kb_repo.set_document_status(doc_id, "done", chunk_count=len(ids))
            logger.info(f"聊天文件已保存到默认知识库: doc_id={doc_id}, file={file_name}, chunks={len(ids)}")
        except Exception as e:
            # 单篇文档入库失败不应影响 OCR 响应，仅记录日志，前台可在默认知识库中看到 error 状态
            logger.exception(f"保存聊天文件到默认知识库失败: {e}")

        
    @app.post("/api/rag/model/download")
    async def rag_model_download():
        """下载 RAG 本地 embedding 模型（smart_download：智能选镜像 + 智能选大小模型）。

        snapshot_download 为阻塞式网络 IO，放入线程池避免卡住事件循环。
        注意：模型体积较大，下载耗时可达分钟级，前端 fetch 不设超时即可。
        返回 model（实际下载的模型仓库 id）与 path（本地目录），供前端写回配置。
        """
        global _rag_download_busy
        if _rag_download_busy:
            raise HTTPException(status_code=409, detail="已有下载任务正在进行，请稍候")
        _rag_download_busy = True
        try:
            result = await asyncio.to_thread(model_download.smart_download)
            logger.info(f"RAG embedding 模型下载完成: {result}")
            return {"status": "success", **result}
        except Exception as e:
            logger.exception("RAG embedding 模型下载失败")
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            _rag_download_busy = False

    @app.get("/api/messages")
    async def api_messages(
        session_id: str = Query(..., description="会话 ID（对应 LangChain thread_id）"),
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    ):
        """分页查询历史消息（含附件）"""
        try:
            items, total = await get_messages_by_session(session_id, page, page_size)
            return {
                "items": items,
                "total": total,
                "page": page,
                "pageSize": page_size,
            }
        except Exception as e:
            logger.exception(f"查询历史消息失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    app.include_router(kb_router)
    app.include_router(stats_router)
    app.include_router(skills_router)

    @app.websocket("/ws/agent")
    async def ws_agent(websocket: WebSocket):
        await ws_agent_endpoint(websocket)

    return app
