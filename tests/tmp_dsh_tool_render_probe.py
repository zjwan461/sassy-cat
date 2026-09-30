# -*- coding: utf-8 -*-
"""临时探测：dsh 工具过程是否按预期渲染成引用块 markdown 流出（用完可删）。

跑一个会触发工具的任务，打印 stream_writer 收到的每个片段（带时间戳）与拼接全文。
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
    def __init__(self, thread_id):
        self.chunks = []
        self.config = {"configurable": {"thread_id": thread_id}}

    def stream_writer(self, chunk):
        self.chunks.append((round(time.monotonic() - T0, 2), chunk.get("text", "")))


async def main():
    fn = getattr(call_dsh, "coroutine", None) or call_dsh.func
    rt = FakeRuntime(f"toolrender-{int(T0)}")

    out = await fn(
        "请创建一个文件 render_probe.txt，内容写 'hi'；然后用 shell 查看当前目录文件列表，"
        "最后用大约 80 字总结你做了什么。",
        rt,
    )
    print(f"[{time.monotonic() - T0:6.2f}s] 工具返回：{out!r}\n"[:160])

    print(f"=== stream_writer 片段（{len(rt.chunks)} 个）===")
    for ts, text in rt.chunks:
        print(f"--- @ {ts:6.2f}s ---")
        print(text, end="")

    print("\n\n=== 拼接全文 ===")
    print("".join(t for _, t in rt.chunks))


asyncio.run(main())