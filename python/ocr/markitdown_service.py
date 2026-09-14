import io
import os

md = None


def init():
    from markitdown import MarkItDown

    global md
    if md is None:
        md = MarkItDown()


async def do_ocr(x_filename: str, file_bytes: bytes):
    init()
    filename = (x_filename or "").strip().lower()
    ext = os.path.splitext(filename)[-1]
    md_text = md.convert_stream(io.BytesIO(file_bytes))
    return {
        "page_content": md_text.markdown,
        "metadata": {
            "filename": x_filename,
            "ext": ext,
            "engine": "markitdown",
            "status": "success",
        },
    }
