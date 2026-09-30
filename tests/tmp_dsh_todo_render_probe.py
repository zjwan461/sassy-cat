# -*- coding: utf-8 -*-
"""临时探测：todo/write 是否被渲染成任务清单、有没有被重复刷屏（用完可删）。

直接驱动 call_dsh（真实 plugin 树 + 真实渲染与去重路径），把 stream_writer
收到的增量收集起来，统计"📋 待办"块的数量与内容。
"""

import asyncio
import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "python"))

from agent.tools.subagent_tool import call_dsh  # noqa: E402

T0 = time.monotonic()

PROMPT = (
    "请先用 todo 工具写下 3 步计划（每步执行一次 shell 的 echo，依次打印 1、2、3），"
    "然后逐步执行，最后用一句话说明完成情况。"
)


class FakeRuntime:
    def __init__(self, thread_id):
        self.chunks = []
        self.config = {"configurable": {"thread_id": thread_id}}

    def stream_writer(self, chunk):
        self.chunks.append((round(time.monotonic() - T0, 2), chunk.get("text", "")))


async def main():
    fn = getattr(call_dsh, "coroutine", None) or call_dsh.func
    rt = FakeRuntime(f"todorender-{int(T0)}")

    out = await fn(PROMPT, rt)

    blocks = [t for _, t in rt.chunks if "📋 待办" in t]
    print(f"chunk 数: {len(rt.chunks)} | 待办块数: {len(blocks)}")
    for i, block in enumerate(blocks, 1):
        print(f"--- 待办块 #{i} ---")
        print(block.rstrip())
    print("压缩提示:", [t.strip() for _, t in rt.chunks if "🗜️" in t])
    print("工具返回:", repr(out)[:120])


asyncio.run(main())