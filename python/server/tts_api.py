# -*- coding: utf-8 -*-
"""本地语音合成（GPT-SoVITS）HTTP 接口。

- ``GET  /api/tts/status``  引擎状态（前端据此决定用本地还是系统语音）
- ``GET  /api/tts/voices``  音色列表
- ``POST /api/tts/say``     合成，返回 ``audio/wav``（也支持 GET，方便浏览器直接调试）
- ``POST /api/tts/voice``   热切换音色
- ``POST /api/tts/preload`` 手动触发加载/预热

失败一律返回 503 + ``detail``，前端收到后应回落 Web Speech，不要卡住对话。
"""

from __future__ import annotations

import logging
import os
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from tts import downloader, service
from tts.gpt_sovits_engine import TTSUnavailable

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tts", tags=["tts"])


class SayRequest(BaseModel):
    text: str = Field(..., description="要合成的文本")
    voice: Optional[str] = Field(None, description="音色名，空则用默认音色")
    speed: Optional[float] = Field(None, ge=0.5, le=2.0, description="语速倍率")


class VoiceRequest(BaseModel):
    name: str = Field(..., description="音色名")


class DownloadRequest(BaseModel):
    packages: Optional[List[str]] = Field(
        None, description="只下载这些包（base-models / g2pw / 音色 source id），空则全部"
    )


def _proxy() -> Optional[str]:
    return os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")


@router.get("/status")
async def tts_status():
    """引擎状态。前端启动时调用一次，决定是否展示本地音色选项。"""
    st = service.status()
    vendor, models = service.roots()
    try:
        missing = downloader.missing_required(vendor, models)
    except Exception:  # noqa: BLE001
        missing = []
    st["modelsReady"] = not missing
    st["missingModels"] = missing[:20]
    st["vendorDir"] = str(vendor)
    st["modelsDir"] = str(models)
    return st


@router.get("/voices")
async def tts_voices():
    return {"voices": service.list_voices()}


@router.post("/preload")
async def tts_preload():
    """手动触发加载（设置页“启用本地语音”时可以立刻给用户反馈）。"""
    try:
        await service.preload()
    except TTSUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))
    return service.status()


async def _do_say(text: str, voice: Optional[str], speed: Optional[float]) -> Response:
    try:
        data = await service.synthesize(text, voice=voice, speed=speed)
    except TTSUnavailable as e:
        # 引擎不可用：让前端回落系统语音
        raise HTTPException(status_code=503, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"音色不存在: {e}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # noqa: BLE001 兜底：合成异常不能变成 500 堆栈
        logger.exception("本地 TTS 合成失败")
        raise HTTPException(status_code=503, detail=f"{type(e).__name__}: {e}")

    # 头部带上采样率，前端播放器可选用于校准
    return Response(
        content=data,
        media_type="audio/wav",
        headers={"Cache-Control": "no-store", "X-Sample-Rate": "32000"},
    )


@router.post("/say")
async def tts_say(req: SayRequest):
    return await _do_say(req.text, req.voice, req.speed)


@router.get("/say")
async def tts_say_get(
    text: str = Query(..., description="要合成的文本"),
    voice: Optional[str] = Query(None),
    speed: Optional[float] = Query(None, ge=0.5, le=2.0),
):
    """GET 版本，方便直接在浏览器里试：/api/tts/say?text=你好"""
    return await _do_say(text, voice, speed)


@router.post("/voice")
async def tts_switch_voice(req: VoiceRequest):
    try:
        return await service.switch_voice(req.name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"音色不存在: {req.name}")
    except TTSUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))


# ---------------------------------------------------------------------------
# 模型按需下载（权重不进仓库）
# ---------------------------------------------------------------------------


@router.get("/download/status")
async def tts_download_status():
    st = downloader.status()
    vendor, models = service.roots()
    st["modelsDir"] = str(models)
    try:
        st["missingModels"] = downloader.missing_required(vendor, models)
    except Exception:  # noqa: BLE001
        st["missingModels"] = []
    return st


@router.post("/download/start")
async def tts_download_start(req: Optional[DownloadRequest] = None):
    if downloader.is_running():
        return downloader.status()
    vendor, models = service.roots()
    return downloader.start(
        vendor, models, (req.packages if req else None), _proxy()
    )


@router.post("/download/cancel")
async def tts_download_cancel():
    return downloader.cancel()