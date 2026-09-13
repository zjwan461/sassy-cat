import config_loader
from config_loader import AppConfig
from ocr.ocr_service import do_ocr as do_docling_ocr
from ocr.markitdown_service import do_ocr as do_markitdown_ocr


def get_ocr_strategy(scene: str):
    config: AppConfig = config_loader.current
    if scene == "chat":
        return config.get("agent.ocrEngine", "markitdown")
    elif scene == "rag":
        return config.get("rag.ocrEngine", "docling")
    else:
        raise ValueError(f"unsupported ocr scene: {scene}")


async def do_ocr(scene: str, x_filename: str, file_bytes: bytes):
    strategy = get_ocr_strategy(scene)
    if strategy == "docling":
        return do_docling_ocr(x_filename, file_bytes)
    elif strategy == "markitdown":
        return do_markitdown_ocr(x_filename, file_bytes)
    else:
        raise ValueError(f"unsupported ocr strategy: {strategy}")
