from deepagents import create_deep_agent
from langchain.messages import AIMessageChunk
from langchain.tools import tool
from deepagents.backends import FilesystemBackend, CompositeBackend
from llms import chat_llm
from constant import DB_URL, SKILLS_DIR
from builtin_tools import get_date_time, internet_search, run_command, run_python

import os

work_dir = os.path.join(os.path.dirname(__file__), "../..")
print(f"工作目录：{work_dir}")


# 在需要多场景backend需要使用
# backend = CompositeBackend(
#     default=sandbox_backend,  # 原有业务后端不变
#     routes={
#         "/large_tool_results/": FilesystemBackend(
#             root_dir="/data/deepagents_large_results"
#         ),
#         # "/skills/": FilesystemBackend(root_dir=local_skill_dir),
#     },
# )

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.memory import MemorySaver

agent = create_deep_agent(
    name="Jarvis",
    model=chat_llm,
    skills=["/skills"],
    tools=[get_date_time, internet_search],
    interrupt_on={
        "run_command": True,
        "run_python": True,
        "write_file": True,
        "edit_file": True,
    },
    backend=FilesystemBackend(root_dir=work_dir, virtual_mode=True),
    checkpointer=MemorySaver(),
    system_prompt="你是一个主管Agent助手，你需要对任务进行拆解，分为多个子任务调用子Agent来处理。最终给我最终答案。",
)


# resp = agent.invoke({"messages": [{"role": "user", "content": "hi"}]})
# print(resp)

current_agent: str = ""
user_prompt = "查询一下深圳明天的天气，并给出穿衣意见"
for _, chunk in agent.stream(
    {"messages": [{"role": "user", "content": user_prompt}]},
    config={"configurable": {"thread_id": "1"}},
    stream_mode="messages",
    subgraphs=True,
):
    msg_chunk = chunk[0]
    metadata = chunk[1]
    cb = msg_chunk.content_blocks
    lc_agent_name = metadata.get("lc_agent_name", "")
    if current_agent != lc_agent_name:
        current_agent = lc_agent_name
        print(f"\nAgent: {current_agent}开始发言：")

    if cb:
        item = cb[0]
        if item.get("type") == "text":
            print(item.get("text"), end="")
        elif item.get("type") == "tool_call_chunk":
            tool_call_id = item.get("id")
            tool_name = item.get("name")
            if tool_call_id:
                print(f"正在调用工具：{tool_name}")
            # else:
            #     print(item)
