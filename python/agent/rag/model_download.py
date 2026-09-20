import logging

import httpx
from huggingface_hub import snapshot_download

logger = logging.getLogger(__name__)

# 网络探测参数
_HF_API_PROBE_URL = "https://huggingface.co/api/models"
_PROBE_TIMEOUT = 5.0  # 秒

# 镜像端点：末尾不要带 "/"。huggingface_hub 对显式传入的 endpoint 不做归一化，
# 带 "/" 会拼出 "https://hf-mirror.com//api/models/..." 这种双斜杠 URL，
# 镜像站会直接返回 404（仓库明明存在也会下载失败）。
_MIRROR_ENDPOINT = "https://hf-mirror.com"

# 大模型显存门槛（GB）
_LARGE_MODEL_MIN_VRAM_GB = 4.0

# 候选模型仓库 id
SMALL_MODEL = "BAAI/bge-small-zh-v1.5"
LARGE_MODEL = "BAAI/bge-large-zh-v1.5"


def _can_reach_huggingface() -> bool:
    """探测 huggingface.co 是否可直连。

    仅做 TCP 握手并不够：受限网络下 443 端口可能握手成功但 HTTPS 请求被拦截/劫持，
    从而误判为"可直连"。这里直接请求一个轻量 API 端点，只有返回 <400 才认为可直连。
    """
    try:
        resp = httpx.get(_HF_API_PROBE_URL, timeout=_PROBE_TIMEOUT, follow_redirects=True)
        return resp.status_code < 400
    except Exception:
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


def _endpoint_for(use_mirror: bool) -> str | None:
    """根据是否走镜像返回 snapshot_download 的 endpoint。

    显式传入的 endpoint 会被 huggingface_hub 原样使用（只有环境变量 HF_ENDPOINT
    会走 rstrip("/")），因此这里统一去掉末尾斜杠，避免出现 "//api/..." 双斜杠。
    """
    endpoint = _MIRROR_ENDPOINT if use_mirror else None
    return endpoint.rstrip("/") if endpoint else None


def download_small_embedding_model(use_mirror: bool = False):
    return snapshot_download(SMALL_MODEL, endpoint=_endpoint_for(use_mirror))


def download_large_embedding_model(use_mirror: bool = False):
    return snapshot_download(LARGE_MODEL, endpoint=_endpoint_for(use_mirror))


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