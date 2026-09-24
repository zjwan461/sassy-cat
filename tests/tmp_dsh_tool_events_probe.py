# -*- coding: utf-8 -*-
"""临时探测：dsh 调用工具时会发哪些 session.event、payload 长啥样（用完可删）。

强制 dsh 走一次工具（写文件 + 跑 shell），把每条 session.event 的 type 与
data 结构（含 stream 分块类型）打印出来，供决定“工具过程怎么流式渲染”。
"""

import json
import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "python"))

from agent.tools.dsh import dsh_invoker  # noqa: E402

T0 = time.monotonic()


def trim(obj, limit=400):
    s = json.dumps(obj, ensure_ascii=False, default=str)
    return s if len(s) <= limit else s[:limit] + "…"


def sink(notification):
    if notification.method != "session.event":
        return
    payload = notification.payload or {}
    event = payload.get("event") or {}
    etype = event.get("type")
    data = event.get("data") or {}
    ts = f"{time.monotonic() - T0:6.2f}s"

    if etype == "assistant/message":
        stream = data.get("stream") or []
        kinds = [s.get("type") for s in stream if isinstance(s, dict)]
        print(f"{ts}  {etype}  stream_types={kinds}")
        for s in stream:
            if isinstance(s, dict) and s.get("type") not in ("text-chunks", "reasoning-chunks", "chunk"):
                print(f"            stream[{s.get('type')}] = {trim(s)}")
        return

    print(f"{ts}  {etype}  data={trim(data)}")


settings = dsh_invoker.load_llm_settings(dsh_invoker.resolve_config_path())
harness = dsh_invoker.build_harness(settings)
with harness:
    result = harness.run(
        "在 /tmp 下别动。请在你当前工作目录创建一个文件 dsh_probe.txt，内容写 'hello dsh'；"
        "创建完成后用 shell 执行 `ls -la` 查看当前目录，并把结果告诉我。",
        session_id=f"toolevt-{int(T0)}",
        on_notification=sink,
    )
print("total:", round(time.monotonic() - T0, 2), "s")
print("finish_reason:", result.finish_reason)
print("final:", trim(result.final_response, 300))