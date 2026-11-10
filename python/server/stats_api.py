# -*- coding: utf-8 -*-
"""
Dashboard 报表 REST API：一次性返回对话/Token/知识库统计与近 N 天趋势。
"""

import logging

from fastapi import APIRouter, HTTPException, Query

from server.db import stats_repository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/dashboard")
async def dashboard_stats(
    trend_days: int = Query(7, ge=1, le=90, description="趋势图天数（含今日）"),
):
    """Dashboard 报表聚合数据（对话次数、Token 用量、知识库规模、逐日趋势）"""
    try:
        return await stats_repository.dashboard_stats(trend_days=trend_days)
    except Exception as e:
        logger.exception("查询 Dashboard 统计失败")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/usage")
async def usage_stats(
    session_limit: int = Query(8, ge=1, le=50, description="返回的会话数"),
):
    """按模型/会话统计 Token、平均耗时与失败率。"""
    try:
        return await stats_repository.usage_stats(session_limit=session_limit)
    except Exception as e:
        logger.exception("查询用量统计失败")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/session")
async def session_stats(
    session_id: str = Query(..., description="会话 ID"),
):
    """聊天页底部统计：轮次/步数、Token、缓存命中、速度与上下文占用。"""
    try:
        return await stats_repository.session_stats(session_id)
    except Exception as e:
        logger.exception("查询会话统计失败")
        raise HTTPException(status_code=500, detail=str(e))
