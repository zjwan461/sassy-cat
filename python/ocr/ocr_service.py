import os

from fastapi import HTTPException

from ocr.doc_service import doc_to_markdown
from ocr.docling_service import docling_to_markdown
from ocr.xls_service import xls_to_markdown
from ocr.other_doc_service import other_to_markdown

import logging

logger = logging.getLogger(__name__)

DOCLING_EXTS = {
    ".pdf",
    ".docx",
    ".xlsx",
    ".pptx",
    ".ppt",
    ".md",
    ".markdown",
    ".html",
    ".xhtml",
    ".csv",
}

TEXT_EXTS = {
    ".json",
    ".txt",
    ".go",
    ".py",
    ".java",
    ".sh",
    ".bat",
    ".ps1",
    ".cmd",
    ".js",
    ".ts",
    ".css",
    ".cpp",
    ".hpp",
    ".h",
    ".c",
    ".cs",
    ".sql",
    ".log",
    ".ini",
    ".pl",
    ".pm",
    ".r",
    ".dart",
    ".dockerfile",
    ".env",
    ".php",
    ".hs",
    ".hsc",
    ".lua",
    ".nginxconf",
    ".conf",
    ".m",
    ".mm",
    ".plsql",
    ".perl",
    ".rb",
    ".rs",
    ".db2",
    ".scala",
    ".bash",
    ".swift",
    ".vue",
    ".svelte",
    ".ex",
    ".exs",
    ".erl",
    ".tsx",
    ".jsx",
    ".hs",
    ".lhs",
}


async def do_ocr(x_filename: str, file_bytes: bytes):
    filename = (x_filename or "").strip().lower()
    ext = os.path.splitext(filename)[-1]
    logger.info(f"文件类型: {ext}")

    # docling支持的文档走 Docling
    if ext in DOCLING_EXTS:
        return await docling_to_markdown(file_bytes, filename)
    # xls格式处理
    elif ext == ".xls":
        return await xls_to_markdown(file_bytes, filename)
    # doc格式处理
    elif ext == ".doc":
        return await doc_to_markdown(file_bytes, filename)
    # 其它格式走手动处理
    elif ext in TEXT_EXTS or is_text_file(file_bytes):
        return await other_to_markdown(file_bytes, filename)
    # 不支持
    else:
        raise HTTPException(status_code=415, detail=f"Unsupported file type: {ext}")


def is_text_file(data: bytes) -> bool:
    """
    判断二进制数据是否为 文本文件（纯文本）
    标准通用方法，适用于绝大多数场景
    """
    if not data:
        return False

    # 文本文件允许的字符：可打印字符 + 换行 / 制表符
    # 排除 0x00-0x08、0x0B-0x0C、0x0E-0x1F 这些二进制控制字符
    text_characters = bytearray(
        {9, 10, 13} | set(range(32, 127)) | set(range(128, 256))
    )

    # 只检查前 8192 字节，避免大文件慢
    check_data = data[:8192]

    # 只要出现非文本字符，就不是文本文件
    for byte in check_data:
        if byte not in text_characters:
            return False
    return True


if __name__ == "__main__":
    with open(r"C:\Users\89712\Desktop\大众银行生成式AI信贷审批文件系统.pdf", "rb") as f:
        file_bytes = f.read()
        import asyncio
        content = asyncio.run(do_ocr("大众银行生成式AI信贷审批文件系统.pdf", file_bytes))["page_content"]
        print(content)
