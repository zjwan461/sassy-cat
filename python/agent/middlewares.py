from langchain.agents.middleware import before_model
from langchain.agents import AgentState
from langgraph.runtime import Runtime
from langchain.messages import RemoveMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from typing import Any
import config_loader


@before_model
def trim_messages(state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
    """Keep only the last few messages to fit context window."""
    messages = state["messages"]

    cfg = config_loader.current()
    memory_window = int(cfg.get("agent.memoryWindow", "50"))

    if len(messages) <= memory_window:
        return None  # No changes needed

    first_msg = messages[0]
    recent_messages = (
        messages[-memory_window:]
        if len(messages) % 2 == 0
        else messages[-memory_window + 1 :]
    )
    new_messages = [first_msg] + recent_messages

    return {"messages": [RemoveMessage(id=REMOVE_ALL_MESSAGES), *new_messages]}
