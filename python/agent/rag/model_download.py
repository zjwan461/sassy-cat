import logging
import socket

from huggingface_hub import snapshot_download

logger = logging.getLogger(__name__)

# 网络探测参数
_HF_HOST = "huggingface.co"
_HF_PORT = 443
_PROBE_TIMEOUT = 5.0  # 秒

# 大模型显存门槛（GB）
_LARGE_MODEL_MIN_VRAM_GB = 4.0

# 候选模型仓库 id
SMALL_MODEL = "BAAI/bge-small-zh-v1.5"
LARGE_MODEL = "BAAI/bge-large-zh-v1.5"


def _can_reach_huggingface() -> bool:
    """探测 huggingface.co:443 是否可直连（TCP 握手，避免 HTTPS 请求开销）"""
    try:
        with socket.create_connection((_HF_HOST, _HF_PORT), timeout=_PROBE_TIMEOUT):
            return True
    except OSError:
        return False


def _has_big_nvidia_gpu() -> bool:
    """判断本机是否存在显存 >= 4GB 的 NVIDIA 显卡。

    复用 monitor.gpu.collect()（NVML -> PDH -> PowerShell 自动降级采集）。
    采集失败或无独显时返回 False（降级为小模型）。
    """
    try:
        from monitor import gpu
        gpus = gpu.collect()
    except Exception:
        logger.warning("GPU 信息采集失败，按无大显存 N 卡处理", exc_info=True)
        return False

    for g in gpus:
        vendor = (g.get("vendor") or "").lower()
        mem = g.get("memTotalGB")
        if vendor == "nvidia" and mem is not None and mem >= _LARGE_MODEL_MIN_VRAM_GB:
            logger.info(f"检测到 NVIDIA 显卡 {g.get('name')}（显存 {mem}GB），将使用大模型")
            return True
    return False


def download_small_embedding_model(use_mirror: bool = False):
    endpoints = "https://hf-mirror.com/" if use_mirror else None
    return snapshot_download(SMALL_MODEL, endpoint=endpoints)


def download_large_embedding_model(use_mirror: bool = False):
    endpoints = "https://hf-mirror.com/" if use_mirror else None
    return snapshot_download(LARGE_MODEL, endpoint=endpoints)


def smart_download():
    """智能判断是否可访问huggingface.co来判断是否使用hf-mirror.com来下载。智能判断本地电脑显卡来判断下载小模型还是大模型。N卡，4G显存以上使用大模型，其它都使用小模型

    返回 {"model": 所选模型仓库 id, "path": 本地模型目录}，供调用方写入配置。
    """
    use_mirror = not _can_reach_huggingface()
    logger.info(
        f"huggingface.co {'可直连' if not use_mirror else '不可达，改用 hf-mirror.com 镜像'}"
    )

    if _has_big_nvidia_gpu():
        path = download_large_embedding_model(use_mirror=use_mirror)
        return {"model": LARGE_MODEL, "path": path}
    path = download_small_embedding_model(use_mirror=use_mirror)
    return {"model": SMALL_MODEL, "path": path}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(smart_download())