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
    in_tool_args = False  # 是否正处于工具参数流式输出中（用于结束换行）
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
            if in_tool_args:
                print()
                in_tool_args = False
            print(f"\nAgent: {current_agent} 开始发言：")

        if cb:
            for item in cb:  # 遍历全部块，避免同帧多块时丢事件
                t = item.get("type")
                if t == "text" or t == "reasoning":
                    if in_tool_args:  # 参数流结束，换行后继续正文
                        print()
                        in_tool_args = False
                    print(item.get(t) or "", end="", flush=True)
                elif t == "tool_call_chunk":
                    if item.get("id"):  # 新工具调用开始
                        if in_tool_args:
                            print()
                        print(f"\n正在调用工具：{item.get('name')}", flush=True)
                        in_tool_args = False
                    args_part = item.get("args")
                    if args_part:
                        # 流式输出参数增量（args 为不完整 JSON 分片，逐段打印）
                        print(args_part, end="", flush=True)
                        in_tool_args = True
                else:
                    print(item)
    if in_tool_args:
        print()


if __name__ == "__main__":
    main()
