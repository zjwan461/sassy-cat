# -*- coding: utf-8 -*-
"""本地语音合成（GPT-SoVITS）服务层。

职责：把 ``tts.gpt_sovits_engine.TTSEngine`` 包装成适合 FastAPI 使用的异步服务，
对上层屏蔽以下几件事：

1. **加载很慢**（约 17 s 加载 + 20 s 预热）→ 放到线程里跑，绝不在事件循环里阻塞
2. **GPU 必须串行** → 一把 asyncio 锁，同时只允许一次合成
3. **加载可能失败**（没有显卡、权重缺失、依赖不全）→ 统一转成 ``TTSUnavailable``，
   由 API 层返回 503，前端自动回落 Web Speech，不影响其它功能
4. **按需启用** → 只有配置里 ``voice.engine`` 是 local/gpt-sovits 时才预加载

对外接口：

    await preload()                     # lifespan 里后台预热
    await synthesize(text, voice, speed) -> wav bytes
    status() / list_voices() / switch_voice(name)
    shutdown()
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional

import config_loader
from tts.gpt_sovits_engine import (
    TTSEngine,
    TTSUnavailable,
    detect_sovits_version,
    get_engine,
    load_voice_config,
)

logger = logging.getLogger(__name__)

#: 视为“使用本地引擎”的 voice.engine 取值
LOCAL_ENGINE_VALUES = ("local", "gpt-sovits")

_engine: Optional[TTSEngine] = None
_voices: Dict[str, Any] = {}
_default_voice: str = ""
_meta_loaded = False
_loading = False
_error: Optional[str] = None

_load_lock = asyncio.Lock()   # 保证只加载一次
_gpu_lock = asyncio.Lock()    # GPU 串行

MAX_TEXT_CHARS = 2000


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------


def _voices_config_path() -> Path:
    return Path(__file__).resolve().parent / "voices.json"


def roots() -> "tuple[Path, Path]":
    """返回 ``(vendor_dir, models_dir)``。

    - ``vendor_dir``：GPT-SoVITS 代码，默认 ``<项目根>/vendor/gpt-sovits``
    - ``models_dir``：权重，来自 ``config.json`` 的 ``voice.modelsDir``；
      留空时用 ``<userData>/models/gpt-sovits``（权重不进仓库、也不进安装包）
    """
    try:
        vendor, models, _, _ = load_voice_config(
            str(_voices_config_path()), _cfg_str("voice.vendorDir"), str(effective_models_dir())
        )
        return vendor, models
    except Exception:  # noqa: BLE001
        fallback = Path(__file__).resolve().parents[2] / "vendor" / "gpt-sovits"
        return fallback, effective_models_dir()


def _cfg_str(key: str) -> Optional[str]:
    try:
        value = config_loader.current().get(key, "") or ""
        return str(value).strip() or None
    except Exception:  # noqa: BLE001
        return None


def effective_models_dir() -> Path:
    """权重目录：config.json > 环境变量 > <userData>/models/gpt-sovits。"""
    configured = _cfg_str("voice.modelsDir")
    if configured:
        return Path(configured)
    env = os.environ.get("GSV_MODELS_DIR")
    if env:
        return Path(env)
    try:
        import paths  # Electron 通过 --data-dir 传入的 userData

        return Path(paths.data_dir()) / "models" / "gpt-sovits"
    except Exception:  # noqa: BLE001
        return Path(__file__).resolve().parents[2] / "vendor" / "gpt-sovits"


def engine_name() -> str:
    """当前配置的语音方案（web-speech / local）。"""
    try:
        return str(config_loader.current().get("voice.engine", "web-speech") or "web-speech")
    except Exception:
        return "web-speech"


def enabled() -> bool:
    return engine_name() in LOCAL_ENGINE_VALUES


def configured_voice() -> Optional[str]:
    """配置里指定的音色名（voice.gsvVoice），空则用 voices.json 的默认音色。"""
    try:
        name = config_loader.current().get("voice.gsvVoice", "") or ""
        return str(name) or None
    except Exception:
        return None


def _ensure_voice_meta() -> None:
    """只读 voices.json 拿到音色清单（不加载模型）。

    这样设置页在引擎还没加载时也能正确显示可选音色；版本号靠读 .pth 前两字节得出，
    毫秒级开销。
    """
    global _voices, _default_voice, _meta_loaded
    if _meta_loaded:
        return
    try:
        _, _, voices, default = load_voice_config(
            str(_voices_config_path()), _cfg_str("voice.vendorDir"), str(effective_models_dir())
        )
        for v in voices.values():
            try:
                v.version = detect_sovits_version(v.sovits)
            except Exception:  # noqa: BLE001 权重文件缺失不该影响列表展示
                v.version = ""
        _voices, _default_voice = voices, default
        _meta_loaded = True
    except Exception:  # noqa: BLE001
        logger.warning("读取 voices.json 失败", exc_info=True)


# ---------------------------------------------------------------------------
# 加载
# ---------------------------------------------------------------------------


async def _ensure_engine(voice: Optional[str] = None) -> TTSEngine:
    """确保引擎已加载；首次调用会阻塞十几秒（在线程里）。"""
    global _engine, _voices, _default_voice, _loading, _error

    if _engine is not None:
        if voice and voice != _engine.voice.name:
            await switch_voice(voice)
        return _engine

    async with _load_lock:
        if _engine is not None:  # 等锁期间别的协程已加载好
            return _engine

        _loading = True
        _error = None
        try:
            target = voice or configured_voice()
            logger.info("正在加载本地 TTS 引擎（首次需 30 s 以上）…")
            vendor, models = roots()
            _engine = await asyncio.to_thread(
                get_engine,
                str(_voices_config_path()),
                target,
                str(vendor),
                str(models),
            )
            _, _models_dir, _voices, _default_voice = await asyncio.to_thread(
                load_voice_config, str(_voices_config_path()), str(vendor), str(models)
            )
            logger.info(
                "本地 TTS 已就绪：音色 %s，可用 %d 个",
                _engine.voice.name,
                len(_voices),
            )
            return _engine
        except TTSUnavailable as e:
            _error = str(e)
            logger.warning("本地 TTS 不可用，将回落系统语音：%s", e)
            raise
        except Exception as e:  # noqa: BLE001 兜底：任何异常都不能拖垮服务
            _error = f"{type(e).__name__}: {e}"
            logger.exception("本地 TTS 加载异常")
            raise TTSUnavailable(_error) from e
        finally:
            _loading = False


async def preload() -> None:
    """lifespan 后台预热。失败只记日志，绝不影响启动。"""
    if not enabled():
        logger.info("voice.engine=%s，跳过本地 TTS 预热", engine_name())
        return
    try:
        await _ensure_engine()
    except Exception as e:  # noqa: BLE001
        logger.warning("本地 TTS 预热失败（不影响其它功能）: %s", e)


async def reload_engine() -> None:
    """配置切换后重新加载（换音色套餐/换设备时用）。"""
    shutdown()
    await _ensure_engine()


def shutdown() -> None:
    global _engine
    if _engine is None:
        return
    try:
        _engine.close()
    except Exception:  # noqa: BLE001
        logger.exception("关闭 TTS 引擎时出错")
    finally:
        _engine = None


# ---------------------------------------------------------------------------
# 合成
# ---------------------------------------------------------------------------


def _to_wav_bytes(sr: int, audio: Any) -> bytes:
    import numpy as np

    arr = np.asarray(audio)
    if arr.size == 0:
        raise TTSUnavailable("合成结果为空")
    if arr.dtype != np.int16:
        arr = (np.clip(arr, -1.0, 1.0) * 32767.0).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(sr))
        w.writeframes(arr.tobytes())
    return buf.getvalue()


async def synthesize(
    text: str,
    voice: Optional[str] = None,
    speed: Optional[float] = None,
) -> bytes:
    """合成一段文本，返回完整的 wav 字节。

    :raises TTSUnavailable: 引擎不可用或合成失败
    :raises KeyError: 指定的音色不存在
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("text 不能为空")
    if len(text) > MAX_TEXT_CHARS:
        raise ValueError(f"单次合成文本过长（{len(text)} > {MAX_TEXT_CHARS} 字），请先分句")

    engine = await _ensure_engine(voice)
    # 引擎内部还有一把 threading 锁，这里再串一把是为了让等待者能被 asyncio 调度
    async with _gpu_lock:
        override: Dict[str, Any] = {}
        if speed:
            override["speed_factor"] = float(speed)
        sr, audio = await asyncio.to_thread(engine.say, text, **override)
    return _to_wav_bytes(sr, audio)


async def switch_voice(name: str) -> Dict[str, Any]:
    """热切换音色（只换参考音频，不重载模型，毫秒级）。"""
    if _engine is None:
        await _ensure_engine(name)
    if name not in _voices:
        raise KeyError(name)
    await asyncio.to_thread(_engine.switch_voice, _voices[name])  # type: ignore[union-attr]
    return {"voice": name}


# ---------------------------------------------------------------------------
# 状态
# ---------------------------------------------------------------------------


def status() -> Dict[str, Any]:
    _ensure_voice_meta()
    engine = _engine
    device = getattr(engine, "device", None)
    return {
        "engine": engine_name(),
        "enabled": enabled(),
        "available": engine is not None,
        "loading": _loading,
        "error": _error,
        "voice": engine.voice.name if engine else None,
        "defaultVoice": _default_voice or None,
        "voices": sorted(_voices) if _voices else [],
        "device": device,
        # 前端据此提示“当前用 CPU 兜底、会慢一些”
        "isCpu": bool(device and str(device).startswith("cpu")),
        "cpuThreads": getattr(engine, "cpu_threads", 0) or None,
        "sampleRate": 32000,
    }


def list_voices() -> List[Dict[str, Any]]:
    """音色列表（前端下拉框用）。引擎未加载时也能返回。"""
    _ensure_voice_meta()
    out: List[Dict[str, Any]] = []
    for name, v in sorted(_voices.items()):
        has_ref = bool(getattr(v, "ref_audio", ""))
        out.append(
            {
                "name": name,
                "version": getattr(v, "version", ""),
                "language": getattr(v, "text_lang", "zh"),
                "hasReferenceAudio": has_ref,
                # 没有参考音频的音色当前不可直接使用（如 zundamon 缺素材）
                "usable": has_ref,
            }
        )
    return out