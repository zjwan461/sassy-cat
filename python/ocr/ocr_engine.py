import config_loader
from config_loader import AppConfig


def warm_up():
    pass


def get_strategy():
    config: AppConfig = config_loader.current
    return config.get("ocr.engine","markitdonw")


async def do_ocr(x_filename: str, file_bytes: bytes):
    pass
