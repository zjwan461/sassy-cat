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
import base64
import mimetypes
import os


def read_image_as_base64(file_path):
    # 检查文件是否存在
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")

    # 读取文件内容
    with open(file_path, "rb") as f:
        file_content = f.read()

    # 获取 MIME 类型
    # mimetypes.guess_type 返回一个元组 (type, encoding)，对于 PNG，type 通常是 'image/png'
    mime_type, _ = mimetypes.guess_type(file_path)
    if mime_type is None:
        # 如果无法确定，可以根据文件扩展名手动指定，或者使用默认值
        # 对于 PNG 文件，通常可以直接设为 'image/png'
        mime_type = "image/png"

    # 将二进制内容编码为 Base64 字符串
    base64_encoded = base64.b64encode(file_content).decode("utf-8")

    return base64_encoded, mime_type


def main():
    load_config("C:\\Users\\89712\\AppData\\Roaming\\sassy-cat\\config.user.json")
    user_prompt = sys.argv[1] if len(sys.argv) > 1 else "hi"
    version, agent = holder.get()
    print(f"[Agent version={version}] user: {user_prompt}")

    # base64_str, mime_type = read_image_as_base64(r"C:\Users\1\Pictures\2.png")

    current_agent = ""
    in_tool_args = False  # 是否正处于工具参数流式输出中（用于结束换行）
    for _, chunk in agent.stream(
        {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        # {"type": "image", "base64": base64_str, "mime_type": mime_type},
                    ],
                }
            ]
        },
        config={"configurable": {"thread_id": "cli-debug"}},
        stream_mode="messages",
        subgraphs=True,
    ):
        msg_chunk = chunk[0]
        metadata = chunk[1]
        if isinstance(msg_chunk, AIMessageChunk):
            usage_metadata = msg_chunk.usage_metadata
            if usage_metadata and usage_metadata is not None:
                print(usage_metadata)
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
