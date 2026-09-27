# -*- coding: utf-8 -*-
"""临时诊断：为什么模型不主动建 todo list（用完可删）。

不走 call_dsh（它会吃掉通知），直接用 build_harness 拿到原始事件，回答两件事：
1) 新的"任务规划"段落是否真的出现在 system/message 里；
2) todo_write 这个工具自带的 description 到底怎么要求（很可能与我们的提示词冲突）。
另外打印本轮是否真的产生了 todo/write 事件。
"""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "python"))

from agent.tools.dsh import dsh_invoker  # noqa: E402

# 与 tmp_dsh_todo_autoplan_probe.py 同一个提示词：不提 todo，但确实是多步任务
PROMPT = (
    "在当前工作目录下创建三个文件 diag_a.txt / diag_b.txt / diag_c.txt，"
    "分别写入 1、2、3，然后逐个读回来确认内容是否正确，"
    "最后用一句话汇报这三个文件的状态。"
)

system_message = ""
tool_descriptions: dict[str, str] = {}
event_types: set[str] = set()


def sink(notification) -> None:
    global system_message
    if notification.method != "session.event":
        return
    event = (notification.payload or {}).get("event") or {}
    etype = event.get("type")
    if not etype:
        return
    event_types.add(etype)
    data = event.get("data") or {}

    if etype == "system/message" and not system_message:
        for block in (data.get("message") or {}).get("content") or []:
            if isinstance(block, dict) and block.get("type") == "text":
                system_message = block.get("text") or ""
    elif etype == "request/header":
        for tool in ((data.get("header") or {}).get("tools") or []):
            name = tool.get("name")
            if name and name not in tool_descriptions:
                tool_descriptions[name] = tool.get("description") or ""


def main() -> None:
    settings = dsh_invoker.load_llm_settings(dsh_invoker.resolve_config_path())
    harness = dsh_invoker.build_harness(settings)

    with harness:
        result = harness.run(
            PROMPT,
            session_id=f"diag-{os.getpid()}",
            on_notification=sink,
        )

    print("finish_reason:", result.finish_reason)
    print("事件类型:", sorted(event_types))
    print("出现 todo/write:", "todo/write" in event_types)

    print("\n=== system/message 是否含新的规划段落 ===")
    for marker in ("任务规划", "第一步就调用 todo_write", "3~7 项", "全量覆盖"):
        print(f"  {marker!r}: {marker in system_message}")
    print(f"  system/message 共 {len(system_message)} 字")

    print("\n=== todo_write 的工具描述（注意它自带的 when-to-use 指引）===")
    print(tool_descriptions.get("todo_write", "(没拿到)"))


main()