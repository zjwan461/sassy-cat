# -*- coding: utf-8 -*-
"""临时探测：改后的 call_dsh 是否不再阻塞事件循环、且增量边跑边写出（用完可删）。

1) 事件循环里跑一个每 0.2s 打点的后台任务：整轮期间应持续打点（对比旧版会停摆）
2) stream_writer 收到的片段应带时间戳，且首段明显早于整轮结束
"""

import asyncio
import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "python"))

from agent.tools.subagent_tool import call_dsh  # noqa: E402

T0 = time.monotonic()


class FakeRuntime:
    """只需 stream_writer 与 config.configurable.thread_id。"""

    def __init__(self, thread_id):
        self.chunks = []
        self.config = {"configurable": {"thread_id": thread_id}}

    def stream_writer(self, chunk):
        self.chunks.append((round(time.monotonic() - T0, 2), chunk.get("text", "")))


async def ticker(stop: asyncio.Event):
    n = 0
    while not stop.is_set():
        await asyncio.sleep(0.2)
        n += 1
        print(f"  tick {n:2d} @ {time.monotonic() - T0:6.2f}s")


async def main():
    fn = getattr(call_dsh, "coroutine", None) or call_dsh.func
    rt = FakeRuntime(f"async-probe-{int(T0)}")

    stop = asyncio.Event()
    task = asyncio.create_task(ticker(stop))
    await asyncio.sleep(0.5)
    print(f"[{time.monotonic() - T0:6.2f}s] 进入 await call_dsh(...)")

    out = await fn("用大约 200 字介绍 Python 的 GIL，分两三段写。", rt)

    print(f"[{time.monotonic() - T0:6.2f}s] 返回：{out!r}"[:120])
    stop.set()
    await task

    print(f"chunk 数: {len(rt.chunks)}")
    for ts, text in rt.chunks[:6]:
        print(f"  {ts:6.2f}s  {text!r}")
    if len(rt.chunks) > 6:
        print("  ...")
    if rt.chunks:
        print(f"首段 @ {rt.chunks[0][0]}s / 末段 @ {rt.chunks[-1][0]}s")


asyncio.run(main())