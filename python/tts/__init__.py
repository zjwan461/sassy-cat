"""进程内语音合成（GPT-SoVITS）。

对外只有三个入口：

    from tts import get_engine, TTSUnavailable

    engine = get_engine()                 # 单例，首次加载约 17 秒（建议启动时预加载）
    sr, audio = engine.say("要念出来的文字")   # 阻塞，返回 (采样率, int16 数组)
    engine.write_wav("out.wav", sr, audio)

    for sr, chunk in engine.say_stream("很长的文字"):   # 流式，首包更快
        ...

设计说明与全部注意事项见 ``docs/gpt-sovits-integration.md``。
"""

from .gpt_sovits_engine import (  # noqa: F401
    DEFAULT_SAMPLE_RATE,
    SUPPORTED_VERSIONS,
    TTSEngine,
    TTSError,
    TTSUnavailable,
    Voice,
    check_runtime,
    detect_sovits_version,
    get_engine,
    load_voice_config,
)

__all__ = [
    "DEFAULT_SAMPLE_RATE",
    "SUPPORTED_VERSIONS",
    "TTSEngine",
    "TTSError",
    "TTSUnavailable",
    "Voice",
    "check_runtime",
    "detect_sovits_version",
    "get_engine",
    "load_voice_config",
]