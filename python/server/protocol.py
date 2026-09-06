# -*- coding: utf-8 -*-
"""
WS 消息信封与常用构造函数。

统一信封：
  { "v": 1, "id": str, "ts": int, "type": str, "payload": dict }
"""

import itertools
import time

_counter = itertools.count(1)
SERVER_PREFIX = "s"


def next_msg_id() -> str:
    return f"{SERVER_PREFIX}{int(time.time())}-{next(_counter)}"


def envelope(msg_type: str, payload: dict, msg_id: str | None = None) -> dict:
    return {
        "v": 1,
        "id": msg_id or next_msg_id(),
        "ts": int(time.time() * 1000),
        "type": msg_type,
        "payload": payload or {},
    }
