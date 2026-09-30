# -*- coding: utf-8 -*-
"""临时探测：复杂任务下 dsh 会不会**主动**先建 todo list（用完可删）。

提示词里完全不提 todo，用来验证 DEFAULT_SYSTEM_PROMPT 的"任务规划"硬规则是否
真的生效。跑两个不同复杂度的任务做对照：
  - 中等：三个文件写 + 读回（模型上一版把这类判成 trivial 直接跳过）
  - 复杂：写脚本 + 跑通 + 修错（真·多步迭代）
"""

import asyncio
import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "python"))

from agent.tools.subagent_tool import call_dsh  # noqa: E402

T0 = time.monotonic()

TASKS = [
    (
        "中等：3 文件写 + 读回",
        "在当前工作目录下创建三个文件 plan_a.txt / plan_b.txt / plan_c.txt，"
        "分别写入 1、2、3，然后逐个读回来确认内容是否正确，最后用一句话汇报。",
    ),
    (
        "复杂：写脚本 + 跑通 + 修错",
        "在当前工作目录写一个 python 脚本 calc.py，实现 add(a, b) 和 div(a, b)"
        "（除零要抛 ValueError），并在文件末尾写一段 __main__ 自测；"
        "然后用 shell 运行这个自测，如果有失败就修好再跑，直到全部通过，最后汇报结果。",
    ),
]


class FakeRuntime:
    def __init__(self, thread_id):
        self.chunks = []
        self.config = {"configurable": {"thread_id": thread_id}}

    def stream_writer(self, chunk):
        self.chunks.append((round(time.monotonic() - T0, 2), chunk.get("text", "")))


async def main():
    fn = getattr(call_dsh, "coroutine", None) or call_dsh.func

    for label, prompt in TASKS:
        rt = FakeRuntime(f"autoplan-{label[:4]}-{int(T0)}")
        started = time.monotonic()
        out = await fn(prompt, rt)

        texts = [t for _, t in rt.chunks]
        blocks = [t for t in texts if "📋 待办" in t]
        todo_calls = [t for t in texts if "`todo_write`" in t]
        other_calls = sorted(
            {
                line.split("`")[1]
                for t in texts
                for line in t.split("\n")
                if "🛠️ 调用工具 `" in line
            }
        )

        print(f"\n===== {label} =====")
        print(
            f"耗时 {round(time.monotonic() - started, 1)}s | chunk {len(texts)} | "
            f"待办块 {len(blocks)} | todo_write 调用 {len(todo_calls)}"
        )
        print("调用过的工具:", other_calls)
        if blocks:
            print("--- 首个待办块 ---")
            print(blocks[0].rstrip())
        print("工具返回:", repr(out)[:140])


asyncio.run(main())