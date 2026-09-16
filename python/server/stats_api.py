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
