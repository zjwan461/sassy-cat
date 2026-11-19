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
    """GPT-SoVITS **代码**目录的默认位置：``<项目根>/vendor/gpt-sovits``。

    刻意**不做同级目录探测**——代码随仓库分发，路径必须可预期：

    1. 显式传入（来自 config.json 的 ``voice.vendorDir``）
    2. 环境变量 ``GSV_VENDOR_DIR``（仅用于临时调试）
    3. ``<项目根>/vendor/gpt-sovits``
    """
    env = os.environ.get("GSV_VENDOR_DIR")
    if env:
        return Path(env)
    return _guess_project_root() / "vendor" / "gpt-sovits"


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


def load_voice_config(
    config_path: str | os.PathLike[str],
    vendor_dir: str | os.PathLike[str] | None = None,
    models_dir: str | os.PathLike[str] | None = None,
) -> Tuple[Path, Path, Dict[str, Voice], str]:
    """读取 voices.json。

    返回 ``(vendor_dir, models_dir, {名字: Voice}, 默认音色名)``。

    - ``vendor_dir``：GPT-SoVITS **代码**目录（随仓库分发）
    - ``models_dir``：**权重**目录（默认等于 vendor_dir；正式运行时由
      ``config.json`` 的 ``voice.modelsDir`` 指向用户数据目录）

    目录优先级：**显式参数（config.json）> voices.json 字段 > 环境变量 > 默认值**。
    """
    cfg_path = Path(config_path)
    raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    vendor = Path(vendor_dir or raw.get("vendor_dir") or _default_vendor_dir())
    models = Path(
        models_dir
        or raw.get("models_dir")
        or os.environ.get("GSV_MODELS_DIR")
        or vendor
    )
    voices = {name: Voice.from_dict(name, d, models) for name, d in raw.get("voices", {}).items()}
    default = raw.get("default_voice") or (next(iter(voices)) if voices else "")
    return vendor, models, voices, default


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


def _merge_conflicting_utils(gpt_dir: Path) -> None:
    """解决顶层模块名 ``utils`` 的冲突。

    GPT-SoVITS 的权重里 pickle 存的是 ``utils.HParams``（``GPT_SoVITS/utils.py``），
    而 sassy-cat 自己的后端也有一个顶层 ``utils.py``（``python/utils.py``）。
    在完整后端进程里，应用先 import 了 ``utils``，于是 ``sys.modules["utils"]`` 指向
    应用那份，``torch.load`` 反序列化时报：

        AttributeError: Can't get attribute 'HParams' on <module 'utils' from 'python\\utils.py'>

    处理办法：把 GPT 的 utils 提升为 ``sys.modules["utils"]``，同时把应用 utils 里
    **不冲突**的符号并入，避免应用侧后续 ``import utils`` 拿到残缺模块。

    注意：应用里已经 `import utils` 过的地方持有的是**旧模块对象的引用**，不受影响。
    """
    app_utils = sys.modules.get("utils")
    gpt_utils_path = (gpt_dir / "utils.py").resolve()

    current = getattr(app_utils, "__file__", None)
    if current and Path(current).resolve() == gpt_utils_path:
        return  # 已经是 GPT 的，无需处理

    sys.modules.pop("utils", None)
    if str(gpt_dir) not in sys.path:
        sys.path.insert(0, str(gpt_dir))
    try:
        import importlib

        gpt_utils = importlib.import_module("utils")
    except Exception:  # noqa: BLE001 退回到原状，别把应用搞坏
        if app_utils is not None:
            sys.modules["utils"] = app_utils
        logger.warning("无法加载 GPT-SoVITS 的 utils，权重反序列化可能失败", exc_info=True)
        return

    if app_utils is not None and app_utils is not gpt_utils:
        for name in dir(app_utils):
            if name.startswith("__"):
                continue
            if not hasattr(gpt_utils, name):
                try:
                    setattr(gpt_utils, name, getattr(app_utils, name))
                except Exception:  # noqa: BLE001
                    pass
        logger.info(
            "检测到顶层模块名冲突：应用与 GPT-SoVITS 各有一个 utils.py，"
            "已把 GPT 的 utils 设为 sys.modules['utils'] 并合并应用侧符号"
        )
    # importlib 已把 gpt_utils 放进 sys.modules["utils"]


def _patch_g2pw_model_dir(models_dir: Path) -> None:
    """把 g2pw 的**相对** model_dir 重定向到 ``models_dir``。

    ``text/chinese2.py`` 在 import 时构造：``G2PWPinyin(model_dir="GPT_SoVITS/text/G2PWModel")``，
    这个相对路径按 cwd 解析。我们不想让代码目录承担可写职责（装到 Program Files 就不可写了），
    所以在 g2pw 的加载函数入口把相对路径改写到 models_dir 下。

    必须是**单点改写**：``G2PWOnnxConverter.__init__`` 通过模块全局名调用该函数，
    改模块属性即可生效，且无需改上游源码。
    """
    try:
        import text.g2pw.onnx_api as g2pw_api
    except Exception:  # noqa: BLE001
        logger.debug("未找到 text.g2pw.onnx_api，跳过 G2PW 路径改写", exc_info=True)
        return

    orig = getattr(g2pw_api, "download_and_decompress", None)
    if orig is None or getattr(orig, "_gptsovits_redirected", False):
        return

    def _redirected(model_dir: str = "G2PWModel/") -> str:
        path = Path(model_dir)
        if not path.is_absolute():
            path = models_dir / path
        return orig(str(path))

    _redirected._gptsovits_redirected = True  # type: ignore[attr-defined]
    g2pw_api.download_and_decompress = _redirected  # type: ignore[assignment]
    logger.debug("g2pw model_dir 相对路径将重定向到 %s", models_dir)


def _patch_hardcoded_paths(models_dir: Path) -> None:
    """修正上游写死的相对权重路径。

    上游有几处把权重路径钉在**代码目录**下（而不是 cwd，也不是配置项）：
    1. ``GPT_SoVITS/sv.py``：``sv_path = "GPT_SoVITS/pretrained_models/sv/..."``
    2. ``GPT_SoVITS/text/LangSegmenter/langsegmenter.py``：用 ``__file__`` 反推 fast_langdetect 目录
    3. ``GPT_SoVITS/text/chinese2.py``：g2pw 的 ``model_dir`` 是相对路径（按 cwd 解析）

    我们把“代码”和“权重”拆成两个目录后，这些都会指错。这里在**不改上游源码、
    不依赖软链接**的前提下把路径改指到 ``models_dir``。
    """
    pretrained = models_dir / "GPT_SoVITS" / "pretrained_models"

    # 0) G2PW：必须最先做，因为下面 import LangSegmenter 可能间接触发中文前端初始化
    _patch_g2pw_model_dir(models_dir)

    # 1) SV 权重
    target = pretrained / "sv" / "pretrained_eres2netv2w24s4ep4.ckpt"
    try:
        import sv as sv_module  # type: ignore

        if hasattr(sv_module, "sv_path"):
            sv_module.sv_path = str(target)
            logger.debug("sv.sv_path -> %s", target)
    except Exception:  # noqa: BLE001 没有这个模块也不该阻塞（v1 用不到 SV）
        logger.debug("未能改写 sv.sv_path（可忽略）", exc_info=True)

    # 2) fast_langdetect 缓存目录
    try:
        # 先显式 import 一次：它 import 时会把 _default_detector 覆盖成代码目录下的路径，
        # 我们必须在这个副作用之后再改，否则等于没改。
        import text.LangSegmenter.langsegmenter  # noqa: F401

        import fast_langdetect.infer as fl_infer

        cache = pretrained / "fast_langdetect"
        if cache.is_dir():
            fl_infer._default_detector = fl_infer.LangDetector(  # type: ignore[attr-defined]
                fl_infer.LangDetectConfig(cache_dir=cache)
            )
            logger.debug("fast_langdetect cache_dir -> %s", cache)
        else:
            logger.warning("缺少 fast_langdetect 模型目录: %s（auto 语种检测将不可用）", cache)
    except Exception:  # noqa: BLE001
        logger.debug("未能改写 fast_langdetect 缓存目录（可忽略）", exc_info=True)


def _patch_torchaudio_load() -> bool:
    """让 ``torchaudio.load`` 在没有 torchcodec 的环境下也能用。

    torchaudio >= 2.9 把 ``torchaudio.load`` 改成了 TorchCodec 实现，而 TorchCodec
    在 Windows 上还需要额外的 FFmpeg 动态库，属于"能装但很脆"的依赖。

    GPT-SoVITS 只用它来读参考音频（``TTS.py:773`` 一行），格式都是 wav。
    这里用 soundfile 提供一个等价实现，避免引入 torchcodec。

    返回 True 表示打了补丁。
    """
    try:
        import torchaudio
    except Exception:
        return False
    try:
        import torchcodec  # noqa: F401

        return False  # 有 torchcodec，用官方实现
    except Exception:
        pass
    try:
        import soundfile as sf
        import torch
    except Exception:
        return False

    def _load_with_soundfile(path, **kwargs):  # noqa: ANN001, ANN003
        data, sr = sf.read(str(path), dtype="float32", always_2d=True)
        return torch.from_numpy(data.T.copy()), sr

    torchaudio.load = _load_with_soundfile  # type: ignore[assignment]
    logger.debug("已用 soundfile 补齐 torchaudio.load（torchaudio>=2.9 需要 torchcodec）")
    return True


def _nltk_en_available() -> bool:
    """判断英文前端依赖的 nltk 数据是否已在本地。

    ``g2p_en`` 会调用 nltk 的 POS 标注器和 cmudict；缺失时 nltk 会**自动联网下载**
    （在离线/代理受限环境下会卡住而不是报错）。所以预热前必须先确认。
    新旧 nltk 的词性标注器名字不同，两个都认。
    """
    try:
        import nltk
    except Exception:
        return False
    have_tagger = False
    for name in ("taggers/averaged_perceptron_tagger_eng", "taggers/averaged_perceptron_tagger"):
        try:
            nltk.data.find(name)
            have_tagger = True
            break
        except Exception:
            continue
    if not have_tagger:
        return False
    try:
        nltk.data.find("corpora/cmudict")
    except Exception:
        return False
    return True


def _tune_cpu_threads() -> int:
    """CPU 推理时限制线程数，给 UI/主流程留一个核。

    可用 ``GSV_CPU_THREADS`` 覆盖（例如用户机器核数很多、想让 TTS 用满）。
    """
    import torch

    env = os.environ.get("GSV_CPU_THREADS", "").strip()
    if env.isdigit() and int(env) > 0:
        n = int(env)
    else:
        n = max(1, (os.cpu_count() or 4) - 1)
    try:
        torch.set_num_threads(n)
    except Exception:  # pragma: no cover
        pass
    return n


def _resolve_device(requested: str, cuda_ok: bool) -> str:
    """把用户请求的设备解析成实际可用设备。

    ``auto`` → 有 CUDA 用 cuda，否则 cpu；显式要 cuda 但环境没有 → **自动回落 cpu**
    （这是给没有独显的用户兜底，而不是直接报错）。
    """
    req = (requested or "auto").strip().lower()
    if req == "auto":
        return "cuda" if cuda_ok else "cpu"
    if req.startswith("cuda") and not cuda_ok:
        logger.warning("请求了 CUDA 但当前环境不可用，自动回落到 CPU 推理（速度约为 GPU 的 1/3~1/4）")
        return "cpu"
    return req


def _open_jtalk_dict_available() -> bool:
    """判断 pyopenjtalk 的词典是否已在本地。

    pyopenjtalk 0.4.x 起不再内置词典，第一次调用日文前端时会去 GitHub 下载
    ``open_jtalk_dic_utf_8-1.11.tar.gz``（约 102 MB）。在离线或代理受限的环境下
    这个下载会**阻塞而不抛异常**，表现为程序卡死。所以预热前必须先确认。
    """
    env = os.environ.get("OPEN_JTALK_DICT_DIR")
    if env:
        return Path(env).is_dir()
    try:
        import importlib.util

        spec = importlib.util.find_spec("pyopenjtalk")
        if spec is None or not spec.origin:
            return False
        return (Path(spec.origin).parent / "open_jtalk_dic_utf_8-1.11").is_dir()
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 引擎
# ---------------------------------------------------------------------------


class TTSEngine:
    """进程内 GPT-SoVITS 推理引擎（线程安全，GPU 串行）。"""

    def __init__(
        self,
        vendor_dir: str | os.PathLike[str],
        voice: Voice,
        models_dir: str | os.PathLike[str] | None = None,
        device: str = "auto",
        is_half: Optional[bool] = None,
        warmup: bool = True,
        warmup_text: str = "准备完成。",
    ) -> None:
        self.vendor_dir = Path(vendor_dir)
        self.models_dir = Path(models_dir) if models_dir else self.vendor_dir
        self.voice = voice
        self.warmup = warmup
        self.warmup_text = warmup_text

        self._tts = None                       # TTS 实例
        self._gpu_lock = threading.Lock()      # GPU 串行
        self._state_lock = threading.Lock()    # 模型切换互斥
        self._loaded = False
        self._cwd_lock = threading.RLock()

        self.runtime_info = check_runtime()
        cuda_ok = bool(self.runtime_info.get("cuda_available"))
        # 没有 CUDA 时自动用 CPU（而不是抛错）；显式 device="cuda" 也走同一条回落路径
        self.device = _resolve_device(device, cuda_ok)
        if is_half is None:
            is_half = cuda_ok and self.device.startswith("cuda")
        if self.device.startswith("cpu"):
            is_half = False                    # CPU 不支持 fp16
            self.cpu_threads = _tune_cpu_threads()
            self.runtime_info["cpu_threads"] = self.cpu_threads
            logger.warning("本地 TTS 使用 CPU 推理（%d 线程），速度明显低于 GPU", self.cpu_threads)
        else:
            self.cpu_threads = 0
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
        targets = [("预热。", "zh")]
        # 英文：g2p_en 依赖 nltk 数据，缺失会触发联网下载并挂住
        if _nltk_en_available():
            targets.append(("warm up.", "en"))
        else:
            logger.warning(
                "未找到 nltk 数据（averaged_perceptron_tagger / cmudict），跳过英文预热。"
                "解决办法：把 nltk_data 放到包的 nltk_data 目录，或设置 NLTK_DATA 环境变量。"
            )
        # 日文要单独判断：pyopenjtalk >=0.4 不内置词典，缺失时会**联网下载 102MB**，
        # 在离线/代理环境下会直接挂住（不抛异常），所以必须提前跳过。
        if _open_jtalk_dict_available():
            targets.append(("ウォームアップ。", "ja"))
        else:
            logger.warning(
                "未找到 open_jtalk 词典，跳过日文预热（日文合成会不可用）。"
                "解决办法：设置环境变量 OPEN_JTALK_DICT_DIR，"
                "或把 open_jtalk_dic_utf_8-1.11 放进 pyopenjtalk 包目录。"
            )
        for text, lang in targets:
            try:
                clean_text(text, lang, "v2ProPlus")
            except Exception as e:
                # 缺依赖（如 pyopenjtalk）不致命，只影响该语种
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

                # 必须在 import TTS 之前处理：权重里的 pickle 需要 utils.HParams
                _merge_conflicting_utils(Path(gsv))

                # 顺手做一次环境约束：全部走本地模型，避免启动时偷偷联网
                os.environ.setdefault("HF_HUB_OFFLINE", "1")
                os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
                # 上游有些模块从环境变量取权重目录（如 text/chinese2.py 的 bert_path），
                # 默认值是**相对路径**。不覆盖的话，一旦 cwd 不在代码目录就会当成
                # HuggingFace repo id 去联网。这里统一改成绝对路径。
                _pretrained = self.models_dir / "GPT_SoVITS" / "pretrained_models"
                os.environ["bert_path"] = str(_pretrained / "chinese-roberta-wwm-ext-large")
                os.environ["cnhubert_base_path"] = str(_pretrained / "chinese-hubert-base")

                try:
                    from TTS_infer_pack.TTS import TTS
                except Exception as e:
                    raise TTSUnavailable(
                        f"导入 TTS_infer_pack 失败（cwd={os.getcwd()}）: {type(e).__name__}: {e}"
                    ) from e

                _patch_torchaudio_load()
                _patch_hardcoded_paths(self.models_dir)

                self._prewarm_text_frontends()

                base = self.models_dir / "GPT_SoVITS" / "pretrained_models"
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
        # 推理期间同样要待在代码目录：中文前端（G2PW）按相对路径找模型，
        # 且这里已被 _gpu_lock 串行化，切 cwd 不会和其它 TTS 调用打架。
        with self._gpu_lock, self._in_vendor():
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
    vendor_dir: str | os.PathLike[str] | None = None,
    models_dir: str | os.PathLike[str] | None = None,
    **kwargs: Any,
) -> TTSEngine:
    """获取全局单例。首次调用会加载模型（约 17 秒，建议放在启动阶段）。

    :param config_path: voices.json 路径，默认 ``<本目录>/voices.json``
    :param voice_name: 指定音色，默认用配置里的 ``default_voice``
    :param vendor_dir / models_dir: 覆盖 voices.json 里的目录（来自 config.json）
    :param kwargs: 透传给 TTSEngine（device / is_half / warmup 等）
    """
    global _ENGINE
    with _ENGINE_LOCK:
        if _ENGINE is not None:
            if voice_name and voice_name != _ENGINE.voice.name:
                _, _, voices, _ = load_voice_config(
                    config_path or _default_config_path(), vendor_dir, models_dir
                )
                if voice_name in voices:
                    _ENGINE.switch_voice(voices[voice_name])
            return _ENGINE

        path = Path(config_path) if config_path else _default_config_path()
        vendor, models, voices, default_name = load_voice_config(path, vendor_dir, models_dir)
        if not voices:
            raise TTSUnavailable(f"{path} 里没有配置任何音色")
        name = voice_name or default_name
        if name not in voices:
            raise TTSUnavailable(f"音色 {name!r} 不存在，可选: {sorted(voices)}")

        _ENGINE = TTSEngine(vendor_dir=vendor, models_dir=models, voice=voices[name], **kwargs)
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

    vendor, models, voices, default_name = load_voice_config(cfg)
    print(f"vendor_dir = {vendor}")
    print(f"models_dir = {models}")
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