# -*- coding: utf-8 -*-
"""
CLI 调试入口（历史 demo 改造）：
  python -m agent.main_agent "查询一下深圳明天的天气，并给出穿衣意见"

线上路径请使用 agent/runner.py（WS 服务经 AgentHolder 调度）。
"""

import sys

from agent.engine import holder
from config_loader import load_config
from langchain.messages import AIMessageChunk


def main():
    load_config("C:\\Users\\1\\AppData\\Roaming\\sassy-cat\\config.user.json")
    user_prompt = sys.argv[1] if len(sys.argv) > 1 else "hi"
    version, agent = holder.get()
    print(f"[Agent version={version}] user: {user_prompt}")

    current_agent = ""
    for _, chunk in agent.stream(
        {"messages": [{"role": "user", "content": user_prompt}]},
        config={"configurable": {"thread_id": "cli-debug"}},
        stream_mode="messages",
        subgraphs=True,
    ):
        msg_chunk = chunk[0]
        metadata = chunk[1]
        cb = msg_chunk.content_blocks
        lc_agent_name = metadata.get("lc_agent_name", "")
        if current_agent != lc_agent_name:
            current_agent = lc_agent_name
            print(f"\nAgent: {current_agent} 开始发言：")

        if cb:
            item = cb[0]
            if item.get("type") == "text":
                print(item.get("text"), end="", flush=True)
            elif item.get("type") == "reasoning":
                print(item.get("reasoning"), end="", flush=True)
            elif item.get("type") == "tool_call_chunk":
                if item.get("id"):
                    print(f"\n正在调用工具：{item.get('name')}")
            else:
                print(item)


if __name__ == "__main__":
    main()
