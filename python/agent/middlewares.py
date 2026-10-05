import asyncio
import logging
import os

from langchain.agents.middleware import before_agent, before_model, wrap_model_call
from langchain.agents.middleware.types import PrivateStateAttr
from langchain.agents import AgentState
from langgraph.runtime import Runtime
from langchain_core.messages import SystemMessage
from langchain.messages import RemoveMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES
import config_loader
from typing import Annotated, Any
from typing_extensions import NotRequired
from agent.constant import USER_ID, WORK_DIR
from agent.models import OwnerProfile
from monitor.service import static_info
from server.db.kb_repository import list_kbs_sync

logger = logging.getLogger(__name__)


class AgentInfoState(AgentState):
    """扩展 agent 状态：before_agent 阶段预渲染运行时元信息，模型调用阶段直接复用。

    metadata 作为中间件内部通道（PrivateStateAttr），不出现在 agent 的输入/输出 schema，
    仅供 load_metadata 写入、inject_metadata 读取，避免每次模型调用都去查库/扫盘。
    """

    metadata: NotRequired[Annotated[str, PrivateStateAttr]]


@before_model
async def trim_messages(state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
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


# 元信息整块边界标记：用于幂等注入（重建时先剥离旧块再拼新块）
INJECT_MARKER = "[运行时元数据]"
# 各子段分隔标记（人类可读的分节标题）
PROFILE_MARKER = "[主人画像]"
SYSTEM_INFO_MARKER = "[系统信息]"
SOFTWARE_MARKER = "[开发软件]"
KB_MARKER = "[知识库]"
SKILL_MARKER = "[技能]"

# 技能根目录：runtime/skills（与 skills_api、create_skill 工具、dsh 共享的同一目录）
SKILLS_ROOT = os.path.join(WORK_DIR, "skills")


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
    if data.get("gender"):
        lines.append(f"- 性别：{data['gender']}")
    if data.get("age") is not None:
        lines.append(f"- 年龄：{data['age']}")
    if data.get("occupation"):
        lines.append(f"- 职业：{data['occupation']}")
    if data.get("location"):
        lines.append(f"- 所在地：{data['location']}")
    if data.get("relationship_status"):
        lines.append(f"- 情感状况：{data['relationship_status']}")
    likes = data.get("likes") or []
    if likes:
        lines.append(f"- 爱好：{'、'.join(likes)}")
    dislikes = data.get("dislikes") or []
    if dislikes:
        lines.append(f"- 不喜欢：{'、'.join(dislikes)}")
    personality = data.get("personality") or []
    if personality:
        lines.append(f"- 性格：{'、'.join(personality)}")
    if data.get("daily_habit"):
        lines.append(f"- 作息习惯：{data['daily_habit']}")
    goals = data.get("goals") or []
    if goals:
        lines.append(f"- 目标：{'、'.join(goals)}")
    important_dates = data.get("important_dates") or []
    if important_dates:
        lines.append(f"- 重要日期：{'、'.join(important_dates)}")
    if data.get("health_notes"):
        lines.append(f"- 健康提醒：{data['health_notes']}")
    return "\n".join(lines)


def _render_kb_section(kbs: list[dict]) -> str:
    """把知识库清单渲染成注入 system message 的文本段；无知识库时返回空串。"""
    if not kbs:
        return ""
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
    return "\n".join(lines)


def _parse_skill_frontmatter(content: str) -> dict:
    """极简 YAML frontmatter 解析（key: value 与 key: > 多行折叠），够 SKILL.md 用。"""
    if not content.startswith("---"):
        return {}
    lines = content.splitlines()
    meta, key, buf = {}, None, []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        # 顶层 key: value
        if line and not line[0].isspace():
            if buf and key:
                meta[key] = " ".join(buf).strip()
            buf = []
            if ":" in line:
                k, v = line.split(":", 1)
                key, raw = k.strip(), v.strip()
                if raw and raw not in (">", "|", ">-", "|-"):
                    meta[key] = raw
                    key = None
        elif line.strip() and key:  # 缩进续行（多行描述）
            buf.append(line.strip())
    if buf and key:
        meta[key] = " ".join(buf).strip()
    return meta


def _scan_skills_sync() -> list[dict]:
    """扫描 runtime/skills，返回 [{name, displayName, description}]（仅含带 SKILL.md 的技能）。"""
    if not os.path.isdir(SKILLS_ROOT):
        return []
    try:
        names = sorted(os.listdir(SKILLS_ROOT), key=str.lower)
    except OSError:
        return []
    items = []
    for name in names:
        if name.startswith("."):
            continue
        skill_dir = os.path.join(SKILLS_ROOT, name)
        if not os.path.isdir(skill_dir):
            continue
        skill_md = os.path.join(skill_dir, "SKILL.md")
        if not os.path.isfile(skill_md):
            continue
        meta = {}
        try:
            with open(skill_md, "r", encoding="utf-8") as f:
                meta = _parse_skill_frontmatter(f.read(8192))
        except (OSError, UnicodeDecodeError):
            meta = {}
        items.append({
            "name": name,
            "displayName": meta.get("name") or name,
            "description": (meta.get("description") or "").strip(),
        })
    return items


def _render_skill_section(skills: list[dict]) -> str:
    """把技能清单渲染成注入 system message 的文本段；无技能时返回空串。"""
    if not skills:
        return ""
    lines = [
        SKILL_MARKER,
        "本喵拥有如下技能（skill），每个技能是沉淀好的可复用工作流。"
        "当主人需求命中某个技能的触发场景时，请先读取其 /skills/<名称>/SKILL.md 获取指引再执行：",
    ]
    for idx, sk in enumerate(skills, 1):
        desc = sk["description"] or "无描述"
        lines.append(
            f"- 第{idx}个技能 | 名称：{sk['name']} | 描述：{desc}"
            f" | 入口：/skills/{sk['name']}/SKILL.md"
        )
    return "\n".join(lines)


def _render_metadata(
    *,
    profile_text: str,
    system_info_text: str,
    software_info_text: str,
    kb_section: str,
    skill_section: str,
) -> str:
    """把各段元信息按固定顺序拼成整块注入文本；全空时返回空串。

    整块以 INJECT_MARKER 打头，作为幂等剥离的唯一边界。
    """
    parts = []
    if profile_text:
        parts.append(f"{PROFILE_MARKER}\n{profile_text}")
    if system_info_text:
        parts.append(f"{SYSTEM_INFO_MARKER}\n{system_info_text}")
    if software_info_text:
        parts.append(f"{SOFTWARE_MARKER}\n{software_info_text}")
    if kb_section:
        parts.append(kb_section)
    if skill_section:
        parts.append(skill_section)
    if not parts:
        return ""
    return INJECT_MARKER + "\n" + "\n\n".join(parts)


async def _collect_metadata(store) -> str:
    """一次性采集主人画像 / 系统信息 / 开发软件 / 知识库 / 技能，并渲染成整块文本。

    同步阻塞操作（sqlite 直读知识库、扫描技能目录）统一用 asyncio.to_thread 包装，
    避免阻塞事件循环；知识库与技能两个 IO 互不依赖，用 asyncio.gather 并行。
    """
    profile = None
    if store is not None:
        # 异步 store：须用 await aget（中间件在事件循环内执行）
        profile = _coerce_profile(await store.aget(("users",), USER_ID))

    system_info_text = _format_system_info(static_info.get())
    software_info_text = _format_software_info(static_info.get_software())

    kbs, skills = await asyncio.gather(
        asyncio.to_thread(list_kbs_sync),
        asyncio.to_thread(_scan_skills_sync),
    )

    return _render_metadata(
        profile_text=_format_profile(profile) if profile else "",
        system_info_text=system_info_text,
        software_info_text=software_info_text,
        kb_section=_render_kb_section(kbs),
        skill_section=_render_skill_section(skills),
    )


@before_agent(state_schema=AgentInfoState)
async def load_metadata(state: AgentInfoState, runtime: Runtime) -> dict[str, Any] | None:
    """agent 启动时（每轮对话进入时）一次性采集并渲染运行时元信息，写入 state 供复用。

    生命周期：这是 before_agent 钩子，仅在每次 agent 运行的起始节点执行一次，
    因此查库/扫盘频率从原来的「每次模型调用」降为「每轮对话一次」；同轮内的多次
    模型调用（含工具循环）都由 inject_metadata 复用这段渲染结果。
    """
    metadata = await _collect_metadata(getattr(runtime, "store", None))
    return {"metadata": metadata}


@wrap_model_call(state_schema=AgentInfoState)
async def inject_metadata(request, handler):
    """把运行时元信息（画像 / 系统信息 / 开发软件 / 知识库 / 技能）整块注入 system message。

    注意：
    - 必须提供异步实现：本项目用 agent.astream() 执行，LangChain 的异步路径只认
      awrap_model_call，只定义同步 wrap_model_call 会直接抛 NotImplementedError；
    - 元信息来自 state 的 metadata（由 before_agent 的 load_metadata 一次性采集并渲染），
      此处不再查库/扫盘；仅当 state 缺失该字段（异常路径）时兜底采集一次；
    - create_agent 传入的 system_prompt 不在 state["messages"] 里，而是独立挂在
      ModelRequest.system_message 上，因此必须用 wrap_model_call 在模型调用前改写请求。
    """
    sys_msg = request.system_message
    if sys_msg is None:
        return await handler(request)

    # 直接复用 before_agent 预渲染好的元信息块；缺失时兜底采集（正常不会走到）
    metadata = (request.state or {}).get("metadata")
    if metadata is None:
        metadata = await _collect_metadata(getattr(request.runtime, "store", None))

    # 幂等处理：先剥离旧的元信息块（以其边界标记为界），再拼接最新内容
    content = str(sys_msg.content)
    base = content.split(INJECT_MARKER, 1)[0].rstrip()

    new_content = base + "\n\n" + metadata if metadata else base

    if new_content == content:
        return await handler(request)  # 内容无变化，原样透传

    return await handler(request.override(system_message=SystemMessage(content=new_content)))
