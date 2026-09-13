from markitdown import MarkItDown
import io

md = MarkItDown()


async def do_ocr(x_filename: str, file_bytes: bytes):
    return md.convert_stream(io.BytesIO(file_bytes))
