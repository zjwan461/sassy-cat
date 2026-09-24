# -*- coding: utf-8 -*-
"""临时探测：call_dsh 的 thread_id -> dsh session 归属与 writer 结构（用完可删）。

writer 现在写的是 {"agent": "dsh", "text": "..."}（runner 的 custom 分支从这里取值），
本脚本验证：结构一致、同一 thread 复用会话、换 thread 换会话。
"""

import asyncio
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "python"))

from agent.tools import subagent_tool  # noqa: E402
from agent.tools.subagent_tool import call_dsh  # noqa: E402


class FakeRuntime:
    """只需 stream_writer 与 config.configurable.thread_id，工具内部就只用这两个。"""

    def __init__(self, thread_id):
        self.chunks = []
        self.config = {"configurable": {"thread_id": thread_id}}

    def stream_writer(self, chunk):
        self.chunks.append(chunk)


async def run(thread_id, prompt):
    runtime = FakeRuntime(thread_id)
    # call_dsh 现在是协程（内部换线程跑阻塞的 harness.run），须在事件循环里调用
    fn = getattr(call_dsh, "coroutine", None) or call_dsh.func
    out = await fn(prompt, runtime)
    texts = [
        chunk.get("text", "") if isinstance(chunk, dict) else str(chunk)
        for chunk in runtime.chunks
    ]
    agents = {
        chunk.get("agent") for chunk in runtime.chunks if isinstance(chunk, dict)
    }
    print(f"--- thread={thread_id}")
    print("chunks:", [repr(c)[:60] for c in runtime.chunks])
    print(
        "全为带 text 的 dict:",
        all(isinstance(c, dict) and "text" in c for c in runtime.chunks),
        "| agents:",
        agents,
    )
    print("joined:", "".join(texts)[:200])
    print("return:", repr(out)[:200])
    return out


async def main():
    await run("probe-thread-c", "我叫阿猫，请记住这个名字，只回复两个字：好的")
    await run("probe-thread-c", "我叫什么名字？只回答名字")
    await run("probe-thread-d", "我叫什么名字？只回答名字")


asyncio.run(main())

print("=== thread -> dsh session ===")
print(subagent_tool._THREAD_SESSIONS)