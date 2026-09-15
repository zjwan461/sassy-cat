# -*- coding: utf-8 -*-
"""
通用工具函数。
"""


def write_file(path: str, data: bytes) -> None:
    """同步写文件（供 asyncio.to_thread 调用，避免阻塞事件循环）"""
    with open(path, "wb") as f:
        f.write(data)
