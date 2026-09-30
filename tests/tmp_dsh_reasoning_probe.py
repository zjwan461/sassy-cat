# -*- coding: utf-8 -*-
"""临时探测：dsh 深度思考是否渲染成「> 💭 深度思考」引用块（用完可删）。

只打印摘要与片段，避免整段 reasoning（可能上百块）刷屏。
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
    rt = FakeRuntime(f"reasoning-{int(T0)}")

    out = await fn("用大约 200 字介绍 Python 的 GIL，分两三段写。", rt)

    joined = "".join(t for _, t in rt.chunks)
    reasoning_blocks = [t for _, t in rt.chunks if t.startswith("> 💭 深度思考")]
    print(f"chunk 数: {len(rt.chunks)} | 思考块数: {len(reasoning_blocks)}")
    print("含「💭 深度思考」:", "💭 深度思考" in joined)
    if reasoning_blocks:
        r = reasoning_blocks[0]
        lines = r.split("\n")
        print(f"首个思考块行数: {len(lines)}（含末尾空行）")
        print("--- 思考块前 12 行 ---")
        print("\n".join(lines[:12]))
        print("--- 思考块末 3 行 ---")
        print("\n".join([ln for ln in lines if ln][-3:]))
    print("--- 拼接尾部（正文）---")
    print(joined[-200:])
    print("工具返回:", repr(out)[:80])


asyncio.run(main())