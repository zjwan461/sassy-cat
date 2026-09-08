# -*- coding: utf-8 -*-
"""
FastAPI 应用：lifespan 内运行 monitor 周期任务与 proactive 调度任务。
"""

import asyncio
import logging
import time

from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from agent import engine as agent_engine
from monitor import service as monitor_service
from ocr.ocr_service import do_ocr
from proactive import scheduler
from server.bus import hub
from server.protocol import envelope
from server.ws_agent import ws_agent_endpoint
from server.db import init_db as init_message_db, close_db as close_message_db
from server.db import get_messages_by_session

logger = logging.getLogger(__name__)

METRICS_INTERVAL = 2.0
_metrics_stop = asyncio.Event()


async def _monitor_loop():
    """周期采集：阻塞采集放 to_thread，兼容 stdout 协议行"""
    while not _metrics_stop.is_set():
        started = time.time()
        try:
            payload = await asyncio.to_thread(monitor_service.collect_once_and_emit)
            # await hub.publish_all(envelope("metrics.snapshot", payload))
        except Exception:
            logger.exception("monitor tick 失败")
        elapsed = time.time() - started
        await asyncio.sleep(max(0.2, METRICS_INTERVAL - elapsed))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 同步初始化（静态信息采集等含阻塞调用）
    await asyncio.to_thread(monitor_service.init_sync)
    # 打开 agent 共享 SQLite 连接（checkpointer/store 复用，shutdown 时统一关闭）
    await asyncio.to_thread(agent_engine.init_db)
    # 初始化消息数据库（SQLAlchemy 异步引擎）
    await init_message_db()
    stop_event = asyncio.Event()
    monitor_task = asyncio.create_task(_monitor_loop())
    proactive_task = asyncio.create_task(scheduler.run_forever(stop_event))
    logger.info("后台任务已启动：monitor_loop / proactive_scheduler")
    yield
    stop_event.set()
    _metrics_stop.set()
    monitor_task.cancel()
    proactive_task.cancel()
    await asyncio.gather(monitor_task, proactive_task, return_exceptions=True)
    await asyncio.to_thread(monitor_service.shutdown_sync)
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
        MAX_SIZE = 20 * 1024 * 1024  # 20MB
        file_bytes = await file.read()
        if len(file_bytes) > MAX_SIZE:
            raise HTTPException(status_code=413, detail="文件大小超过 20MB 限制")
        try:
            result = await do_ocr(file.filename or "unknown", file_bytes)
            return {
                "status": "success",
                "filename": file.filename,
                "markdown": result.get("page_content", ""),
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"OCR 处理失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

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

    @app.websocket("/ws/agent")
    async def ws_agent(websocket: WebSocket):
        await ws_agent_endpoint(websocket)

    return app
