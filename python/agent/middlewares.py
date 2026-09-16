import logging

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
from monitor.service import static_info
from server.db.kb_repository import list_kbs_sync

logger = logging.getLogger(__name__)


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
SYSTEM_INFO_MARKER = "[系统信息]"
SOFTWARE_MARKER = "[开发软件]"


def _format_system_info(info: dict) -> str:
    """把 static_info 字典渲染成注入 system message 的文本段落"""
    if not info:
        return ""
    lines = []
    if info.get("hostname"):
        lines.append(f"- 主机名：{info['hostname']}")
    if info.get("osName"):
        os_arch = info.get("osArch") or ""
        lines.append(f"- 操作系统：{info['osName']} ({os_arch})")
    if info.get("cpuName"):
        cores = info.get("cpuCores") or "?"
        threads = info.get("cpuThreads") or "?"
        lines.append(f"- CPU：{info['cpuName']}（{cores}核{threads}线程）")
    if info.get("gpuNames"):
        gpu_mem = info.get("gpuMemGB") or {}
        for name in info["gpuNames"]:
            mem = gpu_mem.get(name)
            mem_str = f"，显存 {mem}GB" if mem else ""
            lines.append(f"- GPU：{name}{mem_str}")
    if info.get("totalMemGB"):
        lines.append(f"- 内存：{info['totalMemGB']}GB")
    if info.get("bootTime"):
        lines.append(f"- 上次启动：{info['bootTime']}")
    return "\n".join(lines)


def _format_software_info(software: dict) -> str:
    """把 get_software() 返回的字典渲染成注入 system message 的文本段落"""
    if not software:
        return ""
    lines = []
    for name, info in software.items():
        if isinstance(info, dict):
            version = info.get("version", "")
            path = info.get("path", "")
            if version and path:
                lines.append(f"- {name}: {version}（{path}）")
            elif version:
                lines.append(f"- {name}: {version}")
            elif path:
                lines.append(f"- {name}: {path}")
        elif info:
            lines.append(f"- {name}: {info}")
    return "\n".join(lines)


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
def inject_base_info(request, handler):
    """把 store 中的用户画像和系统信息拼接进 system message，供模型高频感知主人信息和硬件环境。

    注意：create_agent 传入的 system_prompt 不在 state["messages"] 里，
    而是独立挂在 ModelRequest.system_message 上，因此必须用 wrap_model_call
    在模型调用前改写请求，而不是 before_model 改 state。
    """
    sys_msg = request.system_message
    if sys_msg is None:
        return handler(request)

    # 获取用户画像
    user_info = _coerce_profile(request.runtime.store.get(("users",), USER_ID))
    profile_text = _format_profile(user_info) if user_info else ""

    # 获取系统信息
    system_info = static_info.get()
    system_info_text = _format_system_info(system_info)

    # 获取用户电脑上安装的开发软件信息情况
    software_info = static_info.get_software()
    software_info_text = _format_software_info(software_info)

    # 幂等处理：先剥离上一次注入的旧段落，再拼接最新内容
    content = str(sys_msg.content)
    # 先剥离画像段
    base = content.split(PROFILE_MARKER, 1)[0].rstrip()
    # 再剥离系统信息段（如果存在）
    base = base.split(SYSTEM_INFO_MARKER, 1)[0].rstrip()
    # 再剥离开发软件段（如果存在）
    base = base.split(SOFTWARE_MARKER, 1)[0].rstrip()

    # 拼接新内容
    parts = [base]
    if profile_text:
        parts.append(f"{PROFILE_MARKER}\n{profile_text}")
    if system_info_text:
        parts.append(f"{SYSTEM_INFO_MARKER}\n{system_info_text}")
    if software_info_text:
        parts.append(f"{SOFTWARE_MARKER}\n{software_info_text}")

    new_content = "\n\n".join(parts) if len(parts) > 1 else base

    if new_content == content:
        return handler(request)  # 内容无变化，原样透传

    return handler(request.override(system_message=SystemMessage(content=new_content)))


# 知识库段分隔标记：用于幂等注入（重建时先剥离旧段再拼新段）
KB_MARKER = "[知识库]"


@wrap_model_call
def inject_kb_info(request, handler):
    """把用户拥有的知识库列表注入 system message，引导模型判断是否需要调用 search_from_kb 搜索知识库。

    注意：
    - 必须保持同步实现：本项目用同步 agent.stream() 执行，langchain 在同步
      路径只组装 wrap_model_call 链，async-only 中间件（仅 awrap_model_call）
      在同步调用下会直接抛 NotImplementedError；
    - 知识库列表用 list_kbs_sync()（标准库 sqlite3 直读），不可在已有运行中
      事件循环的线程里调用 asyncio.run()；
    - 必须在 inject_base_info 之后注册（middleware 按顺序执行），且采用追加
      而非整体替换，避免覆盖原始 system prompt 与画像/系统信息等段落。
    """
    sys_msg = request.system_message
    if sys_msg is None:
        return handler(request)

    # 同步拉取知识库列表（含文档数与分块数，不依赖 async 引擎与事件循环）
    kbs = list_kbs_sync()

    # 幂等处理：先剥离旧的知识库段，再拼接最新内容
    content = str(sys_msg.content)
    base = content.split(KB_MARKER, 1)[0].rstrip()

    if kbs:
        lines = [
            KB_MARKER,
            "用户拥有如下知识库。当问题涉及其中内容时，请调用工具 **search_from_kb** 检索："
            "能对应到下述某个库就传对应 ID，不确定归属时传 \"all\" 全库搜索。"
            "凡引用知识库内容作答，必须在回答末尾用 markdown 有序列表列出「参考来源」，"
            "每项标注来源文件名 + 所属知识库名称（可对照下方 ID/名称核实），禁止编造来源；"
            "完整规范见运行时约束「知识库检索与溯源规范」：",
        ]
        for idx, kb in enumerate(kbs, 1):
            kb_id = kb.get("id", "")
            name = kb.get("name", "未知")
            desc = kb.get("description") or "无描述"
            doc_count = kb.get("docCount", 0)
            chunk_count = kb.get("chunkCount", 0)
            lines.append(
                f"- 第{idx}个知识库 | ID: {kb_id} | 名称：{name} | 描述：{desc}"
                f" | 文档个数：{doc_count} | 分段个数：{chunk_count}"
            )
        new_content = base + "\n\n" + "\n".join(lines)
    else:
        new_content = base

    if new_content == content:
        return handler(request)  # 内容无变化，原样透传

    return handler(request.override(system_message=SystemMessage(content=new_content)))
