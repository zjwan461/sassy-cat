# -*- coding: utf-8 -*-
"""临时探测：dsh 一轮里 session.event 到底怎么到达（用完可删）。

关注两点，决定"流式效果"能不能做：
1) assistant/message 是不是整轮结束才来一次（结算式）
2) 有没有可用于实时流式的增量事件（如 assistant/attempt 反复到达）
"""

import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "python"))

from agent.tools.dsh import dsh_invoker  # noqa: E402

start = time.monotonic()


def sink(notification):
    if notification.method != "session.event":
        return
    event = notification.payload.get("event") or {}
    etype = event.get("type")
    data = event.get("data") or {}
    elapsed = time.monotonic() - start

    extra = ""
    if etype == "assistant/message":
        stream = data.get("stream") or []
        kinds = [
            (s.get("type"), len(s.get("texts") or []))
            for s in stream
            if isinstance(s, dict)
        ]
        extra = f"stream={kinds}"
    elif etype == "assistant/attempt":
        extra = f"data_keys={sorted(data.keys())}"
    elif etype == "request/header":
        extra = "（请求头，含工具清单）"
    print(f"{elapsed:6.2f}s  {etype}  {extra}")


settings = dsh_invoker.load_llm_settings(dsh_invoker.resolve_config_path())
harness = dsh_invoker.build_harness(settings)
with harness:
    result = harness.run(
        "用大约 200 字介绍 Python 的 GIL，分两三段写。",
        on_notification=sink,
    )
print("total:", round(time.monotonic() - start, 2), "s")
print("finish_reason:", result.finish_reason, "| final len:", len(result.final_response))