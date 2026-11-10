import config_loader


def get_ocr_strategy(scene: str):
    config = config_loader.current()
    if scene == "chat":
        return config.get("agent.ocrEngine", "markitdown")
    elif scene == "rag":
        return config.get("rag.ocrEngine", "docling")
    else:
        raise ValueError(f"unsupported ocr scene: {scene}")


async def do_ocr(scene: str, x_filename: str, file_bytes: bytes):
    strategy = get_ocr_strategy(scene)
    # 延迟导入：Docling 会拉起 torch / transformers（启动耗时 10s+），
    # 只有真正处理文档时才需要。
    if strategy == "docling":
        from ocr.ocr_service import do_ocr as do_docling_ocr

        return await do_docling_ocr(x_filename, file_bytes)
    elif strategy == "markitdown":
        from ocr.markitdown_service import do_ocr as do_markitdown_ocr

        return await do_markitdown_ocr(x_filename, file_bytes)
    else:
        raise ValueError(f"unsupported ocr strategy: {strategy}")
