"""GPT-SoVITS 进程内推理适配层（vendor 快照模式）。

设计原则
--------
1. **本文件是整个项目里唯一与 GPT-SoVITS 耦合的地方**。上游代码怎么变，只改这里。
2. 不依赖 HTTP、不依赖外部进程，模型加载在当前进程内，显存常驻（约 1.2 GB）。
3. 对外只暴露少量 API：``get_engine()`` / ``TTSEngine.say()`` / ``TTSEngine.say_stream()``。

读代码前必读的三个硬约束（都是实测出来的，不是猜的）
----------------------------------------------------
A. **cwd 必须是 GPT-SoVITS 仓库根目录**，至少在这三个瞬间：
   - ``import GPT_SoVITS.sv`` 时（它用 ``os.getcwd()`` 拼模块搜索路径，
     否则报 ``ModuleNotFoundError: No module named 'ERes2NetV2'``）
   - 构造 ``TTS`` 加载模型时
   - **首次**处理中文/日文文本时（G2PW / pyopenjtalk 是懒加载的，
     否则报 ``FileNotFoundError: 'GPT_SoVITS/text/G2PWModel_1.1.zip'``）
   本模块的做法：加载阶段临时 chdir 到仓库根，并在那里预热文本前端；
   预热之后就可以把 cwd 还给调用方，后续推理不再依赖 cwd。

B. **首次合成有一次性开销（实测约 19 秒）**。必须用 ``warmup=True``
   在启动时跑一句废话把这笔账吃掉，否则用户第一次点“说话”会以为程序卡死。

C. **GPU 推理必须串行**。``TTS.run()`` 不是线程安全的，且显存不允许并发。
   本模块用一把全局锁保证串行；多个请求请在外层排队，不要并发调用。

典型用法
--------
    from tts import get_engine
    engine = get_engine()                      # 首次调用会加载模型（约 17 s）
    sr, audio = engine.say("你好，我是你的助手。")
    engine.write_wav("out.wav", sr, audio)

    # 或流式（边合成边播，首包更快）
    for sr, chunk in engine.say_stream("很长的回答……"):
        player.write(chunk)

命令行自检
----------
    python python/tts/gpt_sovits_engine.py --selftest
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import threading
import time
import wave
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

#: SoVITS 权重前两字节 → 模型大版本。
#: 只有 Pro / v3 / v4 系列会把 zip 头改写成版本号，v1/v2 仍是原生 ``PK``，需按体积判断。
_HEAD2VERSION = {
    b"00": "v1",
    b"01": "v2",
    b"02": "v3",
    b"03": "v3",      # v3-lora
    b"04": "v4",      # v4-lora
    b"05": "v2Pro",
    b"06": "v2ProPlus",
}

#: 旧格式（PK 头）按体积区分 v1 / v2，阈值取自 GPT_SoVITS/process_ckpt.py。
_V1_MAX_BYTES = 82978 * 1024
_V2_MAX_BYTES = 700 * 1024 * 1024

#: 官方支持推理的版本集合。
SUPPORTED_VERSIONS = ("v1", "v2", "v3", "v4", "v2Pro", "v2ProPlus")

DEFAULT_SAMPLE_RATE = 32000


class TTSError(RuntimeError):
    """TTS 相关错误的基类。"""


class TTSUnavailable(TTSError):
    """TTS 不可用（环境不满足 / 加载失败 / 推理失败）。

    调用方应当捕获它并降级为纯文字输出，而不是让整个 agent 挂掉。
    """


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def detect_sovits_version(sovits_path: str | os.PathLike[str]) -> str:
    """读取 .pth 判断模型大版本，**不加载模型**（毫秒级）。"""
    p = Path(sovits_path)
    if not p.is_file():
        raise FileNotFoundError(f"SoVITS 权重不存在: {p}")
    with p.open("rb") as f:
        head = f.read(2)
    if head in _HEAD2VERSION:
        return _HEAD2VERSION[head]
    size = p.stat().st_size
    if size < _V1_MAX_BYTES:
        return "v1"
    if size < _V2_MAX_BYTES:
        return "v2"
    return "v3"


def _resolve(base: Path, maybe_relative: str) -> str:
    """相对路径按 base 解析，绝对路径原样返回。"""
    q = Path(maybe_relative)
    return str(q if q.is_absolute() else (base / q))


def _guess_project_root() -> Path:
    """``<root>/python/tts/gpt_sovits_engine.py`` → ``<root>``"""
    return Path(__file__).resolve().parents[2]


def _default_vendor_dir() -> Path:
    """vendor 目录查找顺序。

    1. 环境变量 ``GSV_VENDOR_DIR``
    2. 打包后的 ``<root>/vendor/gpt-sovits``
    3. 开发机上的同级仓库 ``<root>/../GPT-SoVITS-v2pro-*``（按名字前缀匹配）
    """
    env = os.environ.get("GSV_VENDOR_DIR")
    if env:
        return Path(env)
    root = _guess_project_root()
    packaged = root / "vendor" / "gpt-sovits"
    if packaged.is_dir():
        return packaged
    for cand in sorted(root.parent.glob("GPT-SoVITS-v*")):
        if (cand / "GPT_SoVITS").is_dir():
            return cand
    return packaged  # 不存在，交给调用方报错


# ---------------------------------------------------------------------------
# 音色配置
# ---------------------------------------------------------------------------


@dataclass
class Voice:
    """一套音色 = 一对权重 + 一条参考音频。

    说明：参考音频决定“像谁”，GPT 权重决定“怎么说”，SoVITS 权重决定“音色细节”。
    三者必须来自同一次训练；换参考音频可以在不重载模型的情况下改变情绪/语气。
    """

    name: str
    gpt: str
    sovits: str
    ref_audio: str
    prompt_text: str = ""       # 为空 = 无参考文本模式（ref_free）
    prompt_lang: str = "zh"
    text_lang: str = "zh"
    speed_factor: float = 1.0
    #: 只读：加载时自动识别
    version: str = field(default="", compare=False)

    @classmethod
    def from_dict(cls, name: str, d: Dict[str, Any], vendor: Path) -> "Voice":
        ref = d.get("ref_audio", "") or ""
        return cls(
            name=name,
            gpt=_resolve(vendor, d["gpt"]),
            sovits=_resolve(vendor, d["sovits"]),
            # 空字符串表示“没有参考音频”，不能解析成 vendor 目录
            ref_audio=_resolve(vendor, ref) if ref else "",
            prompt_text=d.get("prompt_text", ""),
            prompt_lang=d.get("prompt_lang", "zh"),
            text_lang=d.get("text_lang", "zh"),
            speed_factor=float(d.get("speed_factor", 1.0)),
        )


def load_voice_config(config_path: str | os.PathLike[str]) -> Tuple[Path, Dict[str, Voice], str]:
    """读取 voices.json，返回 (vendor_dir, {名字: Voice}, 默认音色名)。"""
    cfg_path = Path(config_path)
    raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    vendor = Path(raw.get("vendor_dir") or _default_vendor_dir())
    voices = {name: Voice.from_dict(name, d, vendor) for name, d in raw.get("voices", {}).items()}
    default = raw.get("default_voice") or (next(iter(voices)) if voices else "")
    return vendor, voices, default


# ---------------------------------------------------------------------------
# 运行时自检
# ---------------------------------------------------------------------------


def check_runtime() -> Dict[str, Any]:
    """检查当前解释器是否真的能跑这个模型，返回诊断信息。

    不满足条件时抛 ``TTSUnavailable``，并给出人能看懂的原因。
    """
    try:
        import torch
    except Exception as e:  # pragma: no cover
        raise TTSUnavailable(
            "当前 Python 环境没有可用的 torch。"
            f"（{type(e).__name__}: {e}）\n"
            "请使用带 CUDA 12.8 的 PyTorch：pip install torch --index-url "
            "https://download.pytorch.org/whl/cu128"
        ) from e

    info: Dict[str, Any] = {
        "python": sys.version.split()[0],
        "torch": torch.__version__,
        "cuda_build": torch.version.cuda,
        "cuda_available": bool(torch.cuda.is_available()),
        "device_name": None,
        "capability": None,
        "sm_in_build": None,
    }

    if info["cuda_available"]:
        info["device_name"] = torch.cuda.get_device_name(0)
        info["capability"] = torch.cuda.get_device_capability(0)
        maj, mi = info["capability"]
        arch = f"sm_{maj}{mi}"
        info["sm_in_build"] = arch in torch.cuda.get_arch_list()
        if not info["sm_in_build"]:
            raise TTSUnavailable(
                f"显卡是 {info['device_name']}（{arch}），但当前 torch 编译时未包含该架构，"
                f"运行会失败。torch={torch.__version__}, 支持的架构={torch.cuda.get_arch_list()}。\n"
                "5060 Ti 属于 sm_120，必须用 cu128 的 torch（2.7 及以上）。"
            )
    else:
        logger.warning("未检测到可用 CUDA，将回落到 CPU 推理（会非常慢）。")

    return info


# ---------------------------------------------------------------------------
# 引擎
# ---------------------------------------------------------------------------


class TTSEngine:
    """进程内 GPT-SoVITS 推理引擎（线程安全，GPU 串行）。"""

    def __init__(
        self,
        vendor_dir: str | os.PathLike[str],
        voice: Voice,
        device: str = "cuda",
        is_half: Optional[bool] = None,
        warmup: bool = True,
        warmup_text: str = "准备完成。",
    ) -> None:
        self.vendor_dir = Path(vendor_dir)
        self.voice = voice
        self.device = device
        self.warmup = warmup
        self.warmup_text = warmup_text

        self._tts = None                       # TTS 实例
        self._gpu_lock = threading.Lock()      # GPU 串行
        self._state_lock = threading.Lock()    # 模型切换互斥
        self._loaded = False
        self._cwd_lock = threading.RLock()

        self.runtime_info = check_runtime()
        if is_half is None:
            is_half = self.runtime_info["cuda_available"]
        if device == "cpu":
            is_half = False                    # CPU 不支持 half
        self.is_half = bool(is_half)

        self.load(voice)

    # -- cwd 管理 ---------------------------------------------------------

    @contextmanager
    def _in_vendor(self) -> Iterator[Path]:
        """把 cwd 临时切到仓库根；退出时还原。

        加锁是因为 cwd 是**进程级**状态，任何线程改了都影响全局。
        """
        with self._cwd_lock:
            prev = os.getcwd()
            os.chdir(self.vendor_dir)
            try:
                yield self.vendor_dir
            finally:
                try:
                    os.chdir(prev)
                except OSError:  # 原目录被删了，退回项目根
                    os.chdir(_guess_project_root())

    def _prewarm_text_frontends(self) -> None:
        """在 cwd 正确时把中/日/英文本前端全部初始化掉。

        这是把“必须永远待在仓库根目录”降级成“只在加载时待一下”的关键。
        实测：预热后切走 cwd，中英日文本处理均正常。
        """
        try:
            from text.cleaner import clean_text
        except Exception as e:  # pragma: no cover
            logger.warning("文本前端导入失败，中文合成可能受限: %s", e)
            return
        for text, lang in (("预热。", "zh"), ("ウォームアップ。", "ja"), ("warm up.", "en")):
            try:
                clean_text(text, lang, "v2ProPlus")
            except Exception as e:
                # 缺日文依赖（pyopenjtalk）等情况不致命，只影响该语种
                logger.debug("预热 %s 文本前端失败（可忽略）: %s", lang, e)

    # -- 加载 / 切换 -------------------------------------------------------

    def load(self, voice: Optional[Voice] = None) -> None:
        """加载（或重新加载）一套权重。耗时约 17 秒。"""
        with self._state_lock:
            if voice is not None:
                self.voice = voice
            v = self.voice

            if not (self.vendor_dir / "GPT_SoVITS").is_dir():
                raise TTSUnavailable(
                    f"找不到 GPT-SoVITS 代码目录: {self.vendor_dir}\n"
                    "请把仓库放到 <项目根>/vendor/gpt-sovits，"
                    "或设置环境变量 GSV_VENDOR_DIR 指向仓库根目录。"
                )

            v.version = detect_sovits_version(v.sovits)
            if v.version not in SUPPORTED_VERSIONS:
                raise TTSUnavailable(f"不认识的 SoVITS 版本: {v.version}")
            logger.info("加载音色 %s（版本 %s）", v.name, v.version)

            t0 = time.time()
            with self._in_vendor():
                gsv = str(self.vendor_dir / "GPT_SoVITS")
                if gsv not in sys.path:
                    sys.path.insert(0, gsv)

                # 顺手做一次环境约束：全部走本地模型，避免启动时偷偷联网
                os.environ.setdefault("HF_HUB_OFFLINE", "1")
                os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

                try:
                    from TTS_infer_pack.TTS import TTS
                except Exception as e:
                    raise TTSUnavailable(
                        f"导入 TTS_infer_pack 失败（cwd={os.getcwd()}）: {type(e).__name__}: {e}"
                    ) from e

                self._prewarm_text_frontends()

                base = self.vendor_dir / "GPT_SoVITS" / "pretrained_models"
                configs = {
                    "custom": {
                        "device": self.device,
                        "is_half": self.is_half,
                        "version": v.version,
                        "t2s_weights_path": v.gpt,
                        "vits_weights_path": v.sovits,
                        "cnhuhbert_base_path": str(base / "chinese-hubert-base"),
                        "bert_base_path": str(base / "chinese-roberta-wwm-ext-large"),
                    }
                }
                try:
                    self._tts = TTS(configs)
                except Exception as e:
                    raise TTSUnavailable(f"加载模型失败: {type(e).__name__}: {e}") from e

            self._loaded = True
            logger.info("模型加载完成，用时 %.1f 秒", time.time() - t0)

            if self.warmup:
                # 一次性开销（CUDA 内核编译等）约 19 秒，必须在这里吃掉
                t1 = time.time()
                try:
                    self.say(self.warmup_text)
                    logger.info("预热合成完成，用时 %.1f 秒", time.time() - t1)
                except Exception as e:
                    logger.warning("预热合成失败（不影响后续使用）: %s", e)

    def switch_voice(self, voice: Voice) -> None:
        """热切换音色：只换参考音频和语种，不重载模型（毫秒级）。"""
        with self._state_lock:
            v = voice
            v.version = self.voice.version if self.voice else ""
            self.voice = v

            if self._tts is not None and v.ref_audio:
                # set_ref_audio 内部会做 3~10 秒校验与特征缓存
                with self._gpu_lock:
                    self._tts.set_ref_audio(v.ref_audio)
        logger.info("已切换音色: %s", voice.name)

    # -- 推理 -------------------------------------------------------------

    def _build_inputs(self, text: str, **override: Any) -> Dict[str, Any]:
        v = self.voice
        inputs: Dict[str, Any] = {
            "text": text,
            "text_lang": v.text_lang,
            "ref_audio_path": v.ref_audio,
            "aux_ref_audio_paths": [],
            "prompt_text": v.prompt_text,
            "prompt_lang": v.prompt_lang,
            "top_k": 15,
            "top_p": 1.0,
            "temperature": 1.0,
            "text_split_method": "cut5",
            "batch_size": 1,
            "split_bucket": True,
            "speed_factor": v.speed_factor,
            "fragment_interval": 0.3,
            "seed": -1,
            # 无参考文本（ref_free）时 batch_infer 不被支持，框架会自己回退并打警告，
            # 这里提前关掉，少一行噪音日志。
            "parallel_infer": bool(v.prompt_text),
            "repetition_penalty": 1.35,
            "sample_steps": 32,          # 仅 v3 生效
            "super_sampling": False,
        }
        inputs.update(override)
        return inputs

    def say(self, text: str, **override: Any) -> Tuple[int, Any]:
        """阻塞合成，返回 ``(采样率, int16 numpy 数组)``。

        注意：这是阻塞调用（单句约 1~1.5 秒）。在 asyncio 里请用
        ``await asyncio.to_thread(engine.say, text)``，不要直接 await。
        """
        chunks: List[Any] = []
        sr = DEFAULT_SAMPLE_RATE
        for chunk_sr, chunk in self.say_stream(text, **override):
            sr = int(chunk_sr)
            chunks.append(chunk)

        import numpy as np

        if not chunks:
            return sr, np.zeros(0, dtype=np.int16)
        audio = np.concatenate(chunks)
        if audio.dtype != np.int16:
            audio = np.clip(audio, -1.0, 1.0)
            audio = (audio * 32767.0).astype(np.int16)
        return sr, audio

    def say_stream(self, text: str, **override: Any) -> Iterator[Tuple[int, Any]]:
        """流式合成，逐片段 ``yield (采样率, int16 片段)``。

        适合“边合成边播放”，首包延迟明显低于等整句合成完。
        """
        if not text or not text.strip():
            return
        if self._tts is None or not self._loaded:
            raise TTSUnavailable("引擎尚未加载")

        inputs = self._build_inputs(text, **override)
        with self._gpu_lock:
            try:
                for chunk_sr, chunk in self._tts.run(inputs):
                    yield int(chunk_sr), chunk
            except Exception as e:
                raise TTSUnavailable(f"推理失败: {type(e).__name__}: {e}") from e

    # -- 输出 -------------------------------------------------------------

    @staticmethod
    def write_wav(path: str | os.PathLike[str], sr: int, audio: Any) -> str:
        """把 ``say()`` 的结果写成 16-bit 单声道 wav。"""
        import numpy as np

        arr = np.asarray(audio)
        if arr.size == 0:
            raise TTSError("音频为空，无法写入")
        if arr.dtype != np.int16:
            arr = (np.clip(arr, -1.0, 1.0) * 32767.0).astype(np.int16)
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(p), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes(arr.tobytes())
        return str(p)

    def close(self) -> None:
        """释放模型与显存。"""
        with self._state_lock:
            self._tts = None
            self._loaded = False
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 单例
# ---------------------------------------------------------------------------

_ENGINE: Optional[TTSEngine] = None
_ENGINE_LOCK = threading.Lock()


def get_engine(
    config_path: str | os.PathLike[str] | None = None,
    voice_name: str | None = None,
    **kwargs: Any,
) -> TTSEngine:
    """获取全局单例。首次调用会加载模型（约 17 秒，建议放在启动阶段）。

    :param config_path: voices.json 路径，默认 ``<本目录>/voices.json``
    :param voice_name: 指定音色，默认用配置里的 ``default_voice``
    :param kwargs: 透传给 TTSEngine（device / is_half / warmup 等）
    """
    global _ENGINE
    with _ENGINE_LOCK:
        if _ENGINE is not None:
            if voice_name and voice_name != _ENGINE.voice.name:
                _, voices, _ = load_voice_config(config_path or _default_config_path())
                if voice_name in voices:
                    _ENGINE.switch_voice(voices[voice_name])
            return _ENGINE

        path = Path(config_path) if config_path else _default_config_path()
        vendor, voices, default_name = load_voice_config(path)
        if not voices:
            raise TTSUnavailable(f"{path} 里没有配置任何音色")
        name = voice_name or default_name
        if name not in voices:
            raise TTSUnavailable(f"音色 {name!r} 不存在，可选: {sorted(voices)}")

        _ENGINE = TTSEngine(vendor_dir=vendor, voice=voices[name], **kwargs)
        return _ENGINE


def _default_config_path() -> Path:
    return Path(__file__).resolve().parent / "voices.json"


def _force_utf8_stdout() -> None:
    """Windows 的 GBK 控制台打印中文/日文路径会抛 UnicodeEncodeError，这里强制 UTF-8。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass


# ---------------------------------------------------------------------------
# CLI 自检
# ---------------------------------------------------------------------------


def _selftest(args: argparse.Namespace) -> int:
    _force_utf8_stdout()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    cfg = args.config or _default_config_path()

    try:
        info = check_runtime()
    except TTSUnavailable as e:
        print(f"[环境检查失败] {e}")
        return 2
    print("运行时:", json.dumps(info, ensure_ascii=False, indent=2))

    vendor, voices, default_name = load_voice_config(cfg)
    print(f"vendor_dir = {vendor}")
    print(f"音色列表   = {sorted(voices)}  默认 = {default_name}")

    for name, v in voices.items():
        try:
            version = detect_sovits_version(v.sovits)
        except Exception as e:
            version = f"<读取失败: {e}>"
        print(f"  - {name:12s} version={version:10s} ref={'有' if v.ref_audio else '无'}")

    try:
        engine = get_engine(cfg, args.voice, warmup=True)
    except TTSUnavailable as e:
        print(f"[加载失败] {e}")
        return 3

    text = args.text or "你好，我是集成进来的语音引擎。现在我在你的程序进程里说话。"
    print(f"合成中: {text}")
    t0 = time.time()
    sr, audio = engine.say(text)
    elapsed = time.time() - t0
    duration = len(audio) / sr if sr else 0.0
    out = Path(args.out or (Path(os.environ.get("TEMP", ".")) / "gsv_selftest.wav"))
    engine.write_wav(out, sr, audio)
    print(
        f"完成: {duration:.2f} 秒音频 / {elapsed:.2f} 秒耗时 / RTF={elapsed / duration:.3f} "
        f"/ {sr} Hz -> {out}"
    )
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    _force_utf8_stdout()
    p = argparse.ArgumentParser(description="GPT-SoVITS 进程内推理自检")
    p.add_argument("--config", help="voices.json 路径")
    p.add_argument("--voice", help="要合成的音色名")
    p.add_argument("--text", help="要合成的文本")
    p.add_argument("--out", help="输出 wav 路径")
    p.add_argument("--selftest", action="store_true", help="跑完整自检")
    args = p.parse_args(argv)
    if not args.selftest:
        p.print_help()
        return 0
    return _selftest(args)


if __name__ == "__main__":
    raise SystemExit(main())