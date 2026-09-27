# -*- coding: utf-8 -*-
"""临时探测：打字机输出的无损性与效果（用完可删）。

验证三件事：
1) 单元级——切片必须无损：把所有碎片按序拼回去与原文完全一致，且每片 1~3 字；
2) 端到端——真实跑一轮 call_dsh，模型正文被打成 1~3 字的碎片；
3) 结构块——工具块/思考块等仍是整块，没有被切碎。
"""

import asyncio
import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "python"))

from agent.tools.subagent_tool import (  # noqa: E402
    _slice_for_typewriter,
    call_dsh,
)

T0 = time.monotonic()


def check_slicing() -> None:
    sample = "你好，世界！hello 打字机效果 test 12345。"
    slices = list(_slice_for_typewriter(sample))
    sizes = sorted({len(s) for s in slices})
    assert "".join(slices) == sample, "切片拼接后与原文不一致"
    assert sizes and min(sizes) >= 1 and max(sizes) <= 3, f"碎片长度越界: {sizes}"
    print(f"[单元] {len(sample)} 字 -> {len(slices)} 片，长度取值 {sizes}，拼接无损 ✓")


class FakeRuntime:
    def __init__(self, thread_id):
        self.chunks = []
        self.config = {"configurable": {"thread_id": thread_id}}

    def stream_writer(self, chunk):
        self.chunks.append((round(time.monotonic() - T0, 2), chunk.get("text", "")))


async def main():
    check_slicing()

    fn = getattr(call_dsh, "coroutine", None) or call_dsh.func
    rt = FakeRuntime(f"typewriter-{int(T0)}")

    out = await fn("用大约 200 字介绍 Python 的 GIL，分两三段写，写完后结束。", rt)

    texts = [t for _, t in rt.chunks]
    fragments = [t for t in texts if 0 < len(t) <= 3]
    blocks = [t for t in texts if len(t) > 3]

    print(f"[端到端] chunk 总数 {len(texts)}：<=3 字的碎片 {len(fragments)} 个，>3 字的整块 {len(blocks)} 个")
    print(f"[端到端] 总耗时 {round(time.monotonic() - T0, 1)}s")
    print(f"[端到端] 拼接后共 {len(''.join(texts))} 字")
    print("--- 前 12 个 chunk ---")
    print([t for t in texts[:12]])
    print("--- 整块示例（应是完整引用块，未被切碎）---")
    for t in blocks[:2]:
        print(repr(t[:200]))
    print("最终回复长度:", len(out))


asyncio.run(main())