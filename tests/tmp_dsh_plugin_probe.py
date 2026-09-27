# -*- coding: utf-8 -*-
"""临时探测：用**真实**的 editor.patch.yml 跑一轮，验证插件全流程（用完可删）。

走 dsh_invoker.build_harness，即和线上完全同一条路径：只挂 PATCH_FILE。
boot 失败（必填 config 缺失 / 依赖服务没人提供）会直接抛 TimeoutError 并带 stderr；
成功则从 request/header 读回模型实际拿到的工具清单，并汇报本轮出现过的事件类型
（重点看 todo/write 有没有来）。
"""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "python"))

from agent.tools.dsh import dsh_invoker  # noqa: E402

tools_seen: list[str] = []
event_types: set[str] = set()
todo_snapshots: list[list[dict]] = []
system_messages: list[str] = []

# 逼它用上待办：先写计划再执行，顺带覆盖 shell 与文件编辑
PROMPT = (
    "请先用 todo 工具写下 3 步计划（每步执行一次 shell 的 echo，依次打印 1、2、3），"
    "然后逐步执行，最后用一句话说明完成情况。"
)


def sink(notification) -> None:
    if notification.method != "session.event":
        return
    event = (notification.payload or {}).get("event") or {}
    etype = event.get("type")
    if not etype:
        return
    event_types.add(etype)
    data = event.get("data") or {}

    if etype == "request/header":
        header = data.get("header") or {}
        for tool in header.get("tools") or []:
            name = tool.get("name")
            if name and name not in tools_seen:
                tools_seen.append(name)
    elif etype == "system/message":
        # 系统提示词：用来确认 DSH_SYSTEM_PROMPT 真的替换掉了 dsh 的英文默认值
        for block in (data.get("message") or {}).get("content") or []:
            if isinstance(block, dict) and block.get("type") == "text":
                text = (block.get("text") or "").strip()
                if text and text not in system_messages:
                    system_messages.append(text)
    elif etype == "todo/write":
        todos = data.get("todos")
        if isinstance(todos, list):
            todo_snapshots.append(todos)


def main() -> None:
    settings = dsh_invoker.load_llm_settings(dsh_invoker.resolve_config_path())
    harness = dsh_invoker.build_harness(settings)  # 与线上同一条路径

    try:
        with harness:
            result = harness.run(
                PROMPT,
                session_id=f"pluginprobe-{os.getpid()}",
                on_notification=sink,
            )
    except Exception as exc:  # 插件装载失败会在这里现形（TimeoutError + stderr）
        print("FAILED:", type(exc).__name__)
        print(str(exc)[:2500])
        raise

    print("finish_reason:", result.finish_reason)
    print("tools:", tools_seen)
    print("events:", sorted(event_types))
    for text in system_messages:
        print("--- system/message ---")
        print(text[:600])
    print(f"todo/write 快照数: {len(todo_snapshots)}")
    for i, todos in enumerate(todo_snapshots, 1):
        pretty = " | ".join(f"{t.get('status')}:{t.get('content')}" for t in todos)
        print(f"  #{i}: {pretty}")


main()