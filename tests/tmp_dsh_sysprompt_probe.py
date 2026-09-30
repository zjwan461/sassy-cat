# -*- coding: utf-8 -*-
"""临时探测：system prompt 的 {shell_guidance} 占位符按平台展开是否正确（用完可删）。

两层验证：
1) 本地——shell_guidance() 在 win32 / darwin / linux 下分别给出对应写法，
   且 load_llm_settings() 产出的 prompt 里不再有 {shell_guidance} 残留；
2) 真实——boot 一次 dsh，把 system/message 读回来，确认发出去的就是展开后的文本。
"""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "python"))

from agent.tools.dsh import dsh_invoker  # noqa: E402

system_message = ""


def sink(notification) -> None:
    global system_message
    if notification.method != "session.event" or system_message:
        return
    event = (notification.payload or {}).get("event") or {}
    if event.get("type") != "system/message":
        return
    for block in ((event.get("data") or {}).get("message") or {}).get("content") or []:
        if isinstance(block, dict) and block.get("type") == "text":
            system_message = block.get("text") or ""


def main() -> None:
    print("=== shell_guidance() 按平台 ===")
    for platform in ("win32", "darwin", "linux"):
        print(f"  {platform}: {dsh_invoker.shell_guidance(platform)}")

    settings = dsh_invoker.load_llm_settings(dsh_invoker.resolve_config_path())
    prompt = settings["system_prompt"]
    print("\n=== load_llm_settings 产出的 prompt ===")
    print("  含残留占位符 {shell_guidance}:", "{shell_guidance}" in prompt)
    print(f"  共 {len(prompt)} 字")

    harness = dsh_invoker.build_harness(settings)
    with harness:
        result = harness.run("回复两个字：好的", session_id=f"sysp-{os.getpid()}", on_notification=sink)

    print("\n=== 真实 system/message ===")
    print("  finish_reason:", result.finish_reason)
    print("  含残留占位符 {shell_guidance}:", "{shell_guidance}" in system_message)
    for line in system_message.split("\n"):
        if "shell" in line:
            print("  shell 行:", line.strip())


main()