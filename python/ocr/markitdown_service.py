from markitdown import MarkItDown
import io
import os

md = MarkItDown()


async def do_ocr(x_filename: str, file_bytes: bytes):
    filename = (x_filename or "").strip().lower()
    ext = os.path.splitext(filename)[-1]
    md_text = md.convert_stream(io.BytesIO(file_bytes))
    return {
        "page_content": md_text,
        "metadata": {
            "filename": x_filename,
            "ext": ext,
            "engine": "markitdown",
            "status": "success",
        },
    }
