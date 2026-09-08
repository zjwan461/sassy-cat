from langchain.agents.middleware import before_model, wrap_model_call
from langchain.agents import AgentState
from langgraph.runtime import Runtime
from langchain_core.messages import SystemMessage
from langchain.messages import RemoveMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES
import config_loader
from typing import Any
from agent.constant import USER_ID
from agent.models import OwnerProfile


@before_model
def trim_messages(state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
    """Keep only the last few messages to fit context window."""
    messages = state["messages"]

    cfg = config_loader.current()
    try:
        memory_window = int(cfg.active_agent_config().get("memoryWindow", 50))
    except (TypeError, ValueError, AttributeError):
        memory_window = 50

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


# 画像段分隔标记：用于幂等注入（重建时先剥离旧画像再拼新画像）
PROFILE_MARKER = "[主人画像]"


def _coerce_profile(item: Any) -> OwnerProfile | None:
    """store 中可能存的是 Item / dict / OwnerProfile，统一转成 OwnerProfile"""
    if item is None:
        return None
    if isinstance(item, OwnerProfile):
        return item
    # langgraph Item 对象（或其 dict 模拟形式 {"value": ...}）取其 value
    value = getattr(item, "value", None)
    if value is None and isinstance(item, dict) and "value" in item:
        value = item["value"]
    if value is None:
        value = item
    if isinstance(value, OwnerProfile):
        return value
    if isinstance(value, dict):
        try:
            return OwnerProfile.model_validate(value)
        except Exception:
            return None
    return None


def _format_profile(profile: OwnerProfile | dict) -> str:
    """把 OwnerProfile（或其 dict 序列化结果）渲染成注入 system message 的文本段落"""
    if isinstance(profile, OwnerProfile):
        data = profile.model_dump()
    else:
        data = profile
    lines = []
    if data.get("master_name"):
        lines.append(f"- 称呼：{data['master_name']}")
    likes = data.get("likes") or []
    if likes:
        lines.append(f"- 爱好：{'、'.join(likes)}")
    dislikes = data.get("dislikes") or []
    if dislikes:
        lines.append(f"- 不喜欢：{'、'.join(dislikes)}")
    if data.get("daily_habit"):
        lines.append(f"- 作息习惯：{data['daily_habit']}")
    return "\n".join(lines)


@wrap_model_call
def inject_user_info(request, handler):
    """把 store 中的用户画像拼接进 system message，供模型高频感知主人信息。

    注意：create_agent 传入的 system_prompt 不在 state["messages"] 里，
    而是独立挂在 ModelRequest.system_message 上，因此必须用 wrap_model_call
    在模型调用前改写请求，而不是 before_model 改 state。
    """
    sys_msg = request.system_message
    if sys_msg is None:
        return handler(request)

    user_info = _coerce_profile(request.runtime.store.get(("users",), USER_ID))
    profile_text = _format_profile(user_info) if user_info else ""

    # 幂等处理：先剥离上一次注入的旧画像段，再拼接最新画像
    content = str(sys_msg.content)
    base = content.split(PROFILE_MARKER, 1)[0].rstrip()
    new_content = (
        f"{base}\n\n{PROFILE_MARKER}\n{profile_text}" if profile_text else base
    )

    if new_content == content:
        return handler(request)  # 画像无变化，原样透传

    return handler(request.override(system_message=SystemMessage(content=new_content)))
