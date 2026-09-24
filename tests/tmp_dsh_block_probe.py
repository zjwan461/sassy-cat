# -*- coding: utf-8 -*-
"""临时探测：dsh 的同步 harness.run 是否会阻塞事件循环（用完可删）。

在事件循环里起一个每 0.2s 打点的后台任务，然后调用同步的 harness.run。
若打点在 run 期间完全停摆、直到 run 返回才继续，即证明阻塞了事件循环——
这意味着 runner 的 custom 流在整段 dsh 执行期间都无法被消费/下发。
"""

import asyncio
import os
import sys
import time
import uuid

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "python"))

from agent.tools.dsh import dsh_invoker  # noqa: E402

T0 = time.monotonic()


async def ticker(stop: asyncio.Event):
    n = 0
    while not stop.is_set():
        await asyncio.sleep(0.2)
        n += 1
        print(f"  tick {n:2d} @ {time.monotonic() - T0:6.2f}s")


async def main():
    settings = dsh_invoker.load_llm_settings(dsh_invoker.resolve_config_path())
    harness = dsh_invoker.build_harness(settings)

    stop = asyncio.Event()
    task = asyncio.create_task(ticker(stop))
    await asyncio.sleep(0.5)
    print(f"[{time.monotonic() - T0:6.2f}s] 准备进入同步的 harness.run（预期阻塞事件循环）")

    with harness:
        result = harness.run(
            "只回复两个字：好的",
            session_id=f"blk-{uuid.uuid4().hex[:8]}",
        )

    print(f"[{time.monotonic() - T0:6.2f}s] harness.run 返回，正文={result.final_response!r}")
    stop.set()
    await task


asyncio.run(main())