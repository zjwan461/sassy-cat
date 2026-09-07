# python/ocr/docling_service.py
"""基于 Docling + RapidOCR 的文档/图片转 Markdown 服务。

要点：
- 模块导入时不做任何模型下载或重量级初始化（惰性单例 + 线程锁）。
- OCR 使用 RapidOCR（内置 PP-OCRv4 中英文 ONNX 模型，首次使用时自动就绪）。
- 支持 PDF（含扫描件整页 OCR）、图片（png/jpg/tif 等）以及
  docx/xlsx/csv/md/pptx/html 等常规文档格式。
"""

import os

# 禁用 huggingface_hub 的 xet 存储后端，避免公开模型下载时出现 401 Unauthorized 错误。
# 必须在导入 docling 相关模块之前设置。
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

import asyncio
import io
import logging
import threading
from pathlib import Path
from docling_core.types.doc import ImageRefMode
from docling.datamodel.base_models import ConversionStatus, InputFormat
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    RapidOcrOptions,
)
from docling.document_converter import (
    DocumentConverter,
    ImageFormatOption,
    PdfFormatOption,
)
from docling_core.types.io import DocumentStream

logger = logging.getLogger(__name__)

# 可接受的部分成功状态（有内容即认为成功）
_OK_STATUSES = {ConversionStatus.SUCCESS, ConversionStatus.PARTIAL_SUCCESS}

# 全局单例初始化，避免重复加载模型
_converter: DocumentConverter | None = None
_converter_lock = threading.Lock()


def _build_ocr_options() -> RapidOcrOptions:
    """构建 RapidOCR 选项。

    不指定 det/cls/rec 模型路径，使用 rapidocr 包内置的 PP-OCRv4
    中英文 ONNX 模型，避免模块级 snapshot_download 阻塞导入或因
    路径不存在而崩溃。
    """
    return RapidOcrOptions(
        lang=["chinese", "english"],
        backend="onnxruntime",
        force_full_page_ocr=True,  # 整页 OCR，覆盖扫描件/图片
        text_score=0.5,
    )


def _build_converter() -> DocumentConverter:
    """创建 Docling 转换器（仅在首次调用时执行，可能触发模型自动下载）。"""
    pdf_pipeline_options = PdfPipelineOptions(
        do_ocr=True,
        do_table_structure=True,
        generate_picture_images=True,
        ocr_options=_build_ocr_options(),
    )
    pdf_pipeline_options.table_structure_options.do_cell_matching = True

    logger.info("初始化 Docling 转换器（RapidOCR 引擎）...")
    converter = DocumentConverter(
        format_options={
            # PDF：布局分析 + OCR + 表格结构
            InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_pipeline_options),
            # 图片：复用 PDF 管线做整页 OCR
            InputFormat.IMAGE: ImageFormatOption(pipeline_options=pdf_pipeline_options),
            # 其余格式（docx/xlsx/csv/md/pptx/html）使用 Docling 默认
            # SimplePipeline 解析，无需在此显式配置。
        }
    )
    logger.info("Docling 转换器初始化完成")
    return converter


def get_doc_converter() -> DocumentConverter:
    """获取全局单例转换器（线程安全的惰性初始化）。"""
    global _converter
    if _converter is None:
        with _converter_lock:
            if _converter is None:  # double-checked locking
                _converter = _build_converter()
    return _converter


def _sync_convert(file_bytes: bytes, filename: str):
    """同步执行转换，供 asyncio.to_thread 调用。"""
    conv = get_doc_converter()
    source = DocumentStream(name=filename, stream=io.BytesIO(file_bytes))
    return conv.convert(source=source)


async def docling_to_markdown(file_bytes: bytes, filename: str):
    """将文档/图片字节流转换为 Markdown。

    :param file_bytes: 文件原始字节
    :param filename: 文件名（含扩展名，用于格式识别）
    :param trace_id: 链路追踪 ID（可选）
    :return: {"page_content": str, "metadata": dict}
    """
    try:
        if not file_bytes:
            raise ValueError("file_bytes is empty")

        logger.info(f"Docling 处理文件: {filename}")
        path = Path(filename.lower())
        result = await asyncio.to_thread(_sync_convert, file_bytes, filename)

        # 状态判断：FAILURE/SKIPPED 或无文档视为失败；PARTIAL_SUCCESS 视为可用
        if result.status not in _OK_STATUSES or result.document is None:
            logger.error(
                f"Docling 转换失败: status={result.status} errors={result.errors} "
            )
            raise RuntimeError(
                f"Docling conversion failed ({result.status}): {result.errors}"
            )

        # 导出 Markdown
        md_text = result.document.export_to_markdown(image_mode=ImageRefMode.EMBEDDED).strip()
        logger.info(
            f"Docling 处理完成 | 状态: {result.status} | 字符数: {len(md_text)} "
        )

        return {
            "page_content": md_text,
            "metadata": {
                "filename": filename,
                "ext": path.suffix,
                "engine": "docling+rapidocr",
                "status": "success",
            },
        }

    except Exception as e:
        logger.error(f"Docling 处理异常: {e}", exc_info=True)
        raise
