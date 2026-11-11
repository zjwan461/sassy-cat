import asyncio
import base64
import hashlib
import io
import logging
import os
import uuid

from langchain.agents.middleware import before_agent, before_model, wrap_model_call
from langchain.agents.middleware.types import PrivateStateAttr
from langchain.agents import AgentState
from langgraph.runtime import Runtime
from langchain_core.messages import SystemMessage
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


# 旧的 trim_messages（按 memoryWindow 条数裁剪）已移除：
# 它会在摘要触发前先截断历史，导致摘要只看到残缺历史、甚至永远不触发；
# 上下文收敛统一交给 token 驱动的 SummarizationMiddleware（见 engine._build_middleware）。


# ========================= 对话历史里的媒体块守卫 =========================
# 问题：read_file 读图片时，deepagents 的 FilesystemMiddleware 会把整张图以 base64
# 塞进 ToolMessage 的 content 块（用户上传的附件同理进入 HumanMessage）。而框架里
# 每一处「token / 体积」启发式都刻意跳过二进制块，于是没有任何环节会管它：
#   - langchain_core.count_tokens_approximately：image 块固定只算 85 token，base64 一字符不计；
#   - langchain SummarizationMiddleware：按上面的计数判定阈值，永远不会因图片触发压缩；
#   - deepagents 大工具结果外迁：只用文本长度判定（_extract_text_from_message）；
#   - deepagents 消息驱逐：同样只量文本块。
# 后果：图片只进不出。之后每一轮模型调用都要把历史里所有图片的 base64 重新发一遍，
# 上下文占用随「读图次数」线性增长，直到上游直接报「上下文超长 / 请求体过大」。
# 本地网关常按字符数折 token，一张几百 KB 的截图就足以打爆窗口。本中间件补上这一环。
MEDIA_BLOCK_TYPES = frozenset({"image", "image_url", "audio", "video", "file"})
# 媒体块换成的文本占位前缀（模型据此知道"这里原本有图、怎么重新拿到"）
MEDIA_ELIDED_PREFIX = "[媒体已省略]"
_MEDIA_KIND_CN = {
    "image": "图片",
    "image_url": "图片",
    "audio": "音频",
    "video": "视频",
    "file": "文件",
}


def _as_int(value: Any, default: int) -> int:
    """宽松解析整数配置，非法值回退默认（与 engine._as_int 同款语义）"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _media_guard_config() -> dict[str, int]:
    """读取 llm.profiles.<active>.contextCompression 下的媒体守卫参数。

    策略对齐 dsh 的 image offload：**默认全量保留，靠逐张压缩控制体积**，
    只有历史内联媒体总量超出预算时，才从最旧的一端整批 offload。

    max_bytes     单张图片压缩后的目标字节数
    max_px        单张图片压缩后的最长边像素
    budget_bytes  历史内联媒体总字节预算；0 = 不限
    budget_images 历史内联图片总张数预算；0 = 不限
    offload_bytes 触发裁剪时一次释放的字节额度（阶梯式高水位，
                  避免每加一张图就改写旧前缀、打断 KV cache）
    """
    try:
        profile = config_loader.current().active_llm_profile() or {}
        cc = profile.get("contextCompression") or {}
        if not isinstance(cc, dict):
            cc = {}
    except (AttributeError, TypeError):
        cc = {}
    return {
        "max_bytes": max(0, _as_int(cc.get("mediaMaxKB"), 1024)) * 1024,
        "max_px": max(256, _as_int(cc.get("mediaMaxPx"), 1568)),
        "budget_bytes": max(0, _as_int(cc.get("mediaBudgetKB"), 8192)) * 1024,
        "budget_images": max(0, _as_int(cc.get("mediaMaxImages"), 24)),
        "offload_bytes": max(0, _as_int(cc.get("mediaOffloadKB"), 1024)) * 1024,
    }


def _blocks_of(message: Any) -> list:
    """取消息的 content 块列表；纯字符串内容（无多模态块）返回空列表"""
    content = getattr(message, "content", None)
    return content if isinstance(content, list) else []


def _parse_data_url(url: str) -> tuple[str, str] | None:
    """拆 `data:<mime>[;base64],<payload>`，返回 (载荷, mime)；无法拆分返回 None"""
    try:
        header, payload = url.split(",", 1)
    except ValueError:
        return None
    mime = header[5:].split(";")[0] if header.startswith("data:") else ""
    return payload, (mime or "application/octet-stream")


def _media_payload(block: Any) -> tuple[str, str] | None:
    """取出媒体块的「内联载荷」与其 MIME；非内联媒体块返回 None。

    只认真正占上下文的内联形式：
      1) 标准块 {"type": "image", "base64": "...", "mime_type": "..."}
      2) OpenAI 风格 {"type": "image_url", "image_url": {"url": "data:...;base64,..."}}
      3) 归一化后的 {"type": "image", "url": "data:..."}
    url / file_id 这类引用型块由服务端自己取图，不占上下文，原样保留。
    """
    if not isinstance(block, dict):
        return None
    raw = block.get("base64")
    if isinstance(raw, str) and raw:
        return raw, (block.get("mime_type") or "application/octet-stream")
    for key in ("url", "image_url"):
        value = block.get(key)
        if isinstance(value, dict):
            value = value.get("url")
        if isinstance(value, str) and value.startswith("data:"):
            return _parse_data_url(value)
    return None


def _payload_bytes(block: Any) -> int:
    """估算块内联载荷对应的原始字节数（base64 → ×3/4，用于体积判定与日志）"""
    info = _media_payload(block)
    if info is None:
        return 0
    return len(info[0]) * 3 // 4


def _media_mime(block: Any) -> str:
    info = _media_payload(block)
    return info[1] if info else "unknown"


def _elide_block(block: Any, message: Any) -> dict:
    """把媒体块换成人可读、模型可恢复的文本占位（带原始路径，供 read_file 重新取回）"""
    kind = block.get("type") if isinstance(block, dict) else "image"
    kind_cn = _MEDIA_KIND_CN.get(kind, "媒体")
    size_kb = _payload_bytes(block) // 1024
    kwargs = getattr(message, "additional_kwargs", None) or {}
    path = kwargs.get("read_file_path") if isinstance(kwargs, dict) else None
    if path:
        text = (
            f"{MEDIA_ELIDED_PREFIX}为节省上下文，这里原本的{kind_cn}（{path}，"
            f"{_media_mime(block)}，约 {size_kb}KB）已移除。需要再次查看时，"
            f"请用 read_file 重新读取该路径。"
        )
    else:
        text = (
            f"{MEDIA_ELIDED_PREFIX}为节省上下文，这条消息里原本的{kind_cn}"
            f"（{_media_mime(block)}，约 {size_kb}KB）已移除。如仍需查看，"
            f"请让主人重新发送。"
        )
    return {"type": "text", "text": text}


def _shrink_image_block(block: Any, *, max_px: int, quality: int) -> dict | None:
    """把图片块降采样并重编码为 JPEG，返回同形状的新块；不适用 / 失败返回 None。

    同步阻塞（PIL 解码整图），调用方须用 asyncio.to_thread 包装。
    保持原有块形状（base64 字段 / image_url data URL / url data URL）只换载荷，
    避免改变下游 translator 的归一化路径。
    """
    if not isinstance(block, dict) or not _media_mime(block).startswith("image/"):
        return None
    info = _media_payload(block)
    if info is None:
        return None
    try:
        from PIL import Image
    except Exception:  # noqa: BLE001 — 缺 Pillow 时退化为占位，不能影响主流程
        logger.warning("Pillow 不可用，超大图片无法降采样，退化为文本占位")
        return None
    try:
        raw = base64.b64decode(info[0], validate=False)
        with Image.open(io.BytesIO(raw)) as img:
            if img.mode in ("RGBA", "LA", "P"):
                # 透明区压到白底，否则转 JPEG 后会变黑
                rgba = img.convert("RGBA")
                canvas = Image.new("RGB", rgba.size, (255, 255, 255))
                canvas.paste(rgba, mask=rgba.split()[-1])
                img = canvas
            else:
                img = img.convert("RGB")
            if max(img.size) > max_px:
                scale = max_px / max(img.size)
                img = img.resize(
                    (max(1, round(img.width * scale)), max(1, round(img.height * scale))),
                    Image.LANCZOS,
                )
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality, optimize=True)
    except Exception:  # noqa: BLE001 — 解码/编码失败同样退化为占位
        logger.warning("图片降采样失败（损坏或非常规编码），退化为文本占位", exc_info=True)
        return None

    payload = base64.b64encode(buf.getvalue()).decode("ascii")
    new_mime = "image/jpeg"
    if isinstance(block.get("base64"), str):
        return {**block, "base64": payload, "mime_type": new_mime}
    image_url = block.get("image_url")
    if isinstance(image_url, dict):
        return {**block, "image_url": {**image_url, "url": f"data:{new_mime};base64,{payload}"}}
    if isinstance(block.get("url"), str):
        return {**block, "url": f"data:{new_mime};base64,{payload}", "mime_type": new_mime}
    return None


# 质量阶梯（对齐 dsh 的 85/75/60）：从高到低尝试，取第一个满足目标字节的产物；
# 都不满足时保留最小产物——始终保图，不因「压不到目标」把图删掉。
_JPEG_QUALITY_LADDER = (85, 75, 60)
# 记录「已经是我们压过但仍未达到目标」的图片载荷哈希：
# 这类图（内容复杂、压不下去）下一次不再重复编码，避免每轮白烧 CPU。
_COMPRESSED_IMAGE_HASHES: set[str] = set()
_COMPRESSED_HASH_LIMIT = 512


def _remember_compressed(payload: str) -> None:
    if len(_COMPRESSED_IMAGE_HASHES) >= _COMPRESSED_HASH_LIMIT:
        _COMPRESSED_IMAGE_HASHES.clear()
    _COMPRESSED_IMAGE_HASHES.add(hashlib.sha256(payload.encode("ascii", "ignore")).hexdigest())


def _is_known_compressed(payload: str) -> bool:
    return hashlib.sha256(payload.encode("ascii", "ignore")).hexdigest() in _COMPRESSED_IMAGE_HASHES


def _compress_image_block(block: Any, *, max_px: int, target_bytes: int) -> dict | None:
    """把单张图片压到「最长边 ≤ max_px 且字节 ≤ target_bytes」；已达标返回 None。

    这与 dsh 的 request-image 处理同构：先按最长边等比缩放，再走质量阶梯，
    取满足目标的最小产物；压不到目标也保留最小产物（**永不因为太大而丢图**）。

    幂等：已经是 JPEG 且字节达标时直接跳过，重复调用不会反复重编码。
    """
    if not isinstance(block, dict) or not _media_mime(block).startswith("image/"):
        return None
    info = _media_payload(block)
    if info is None:
        return None
    if target_bytes <= 0 and max_px <= 0:
        return None

    original_bytes = len(info[0]) * 3 // 4
    if _is_known_compressed(info[0]):
        return None
    if info[1] == "image/jpeg" and target_bytes > 0 and original_bytes <= target_bytes:
        return None

    best: dict | None = None
    best_bytes = original_bytes
    ladder = _JPEG_QUALITY_LADDER if target_bytes > 0 else (85,)
    for quality in ladder:
        candidate = _shrink_image_block(block, max_px=max_px, quality=quality)
        if candidate is None:
            break
        size = _payload_bytes(candidate)
        if size < best_bytes:
            best, best_bytes = candidate, size
        if target_bytes > 0 and size <= target_bytes:
            break

    if best is None:
        return None
    # 压完反而更大（原图本来就是高压缩比）时保留原图
    if best_bytes >= original_bytes:
        return None
    best_info = _media_payload(best)
    if best_info is not None:
        _remember_compressed(best_info[0])
    return best


@before_model
async def trim_media_history(state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
    """收敛历史里的内联媒体块，策略对齐 dsh 的 image offload。

    规则（幂等）：

    1. **逐张压缩**：所有内联图片都按最长边 `mediaMaxPx`、单图目标 `mediaMaxKB`
       重新编码（JPEG 质量阶梯 85/75/60，取满足目标的最小产物）。压不到目标也保留
       最小产物，绝不因为"太大"直接丢图。
    2. **总量预算**：历史内联媒体总字节超过 `mediaBudgetKB`，或图片张数超过
       `mediaMaxImages` 时，才从**最旧的一端**开始 offload；一次释放
       `mediaOffloadKB` 的额度（阶梯式高水位），避免每来一张新图就改写旧前缀。
    3. 被 offload 的块换成带原始路径的文本占位，模型可用 read_file 重新取回。

    与旧实现的关键差别：不再使用 `mediaKeep` 的「每个来源只留 1 条消息」。
    图片默认全量保留，只有总预算真的爆了才丢弃最旧的媒体。
    """
    messages = state.get("messages") or []
    if not messages:
        return None

    conf = _media_guard_config()
    if (
        conf["max_bytes"] <= 0
        and conf["max_px"] <= 0
        and conf["budget_bytes"] <= 0
        and conf["budget_images"] <= 0
    ):
        return None

    # 先把每条消息的 content 块复制出来，后续压缩 / offload 都在这份副本上做
    blocks_by_idx: list[list | None] = []
    for message in messages:
        blocks = _blocks_of(message)
        if not blocks or not any(_media_payload(b) is not None for b in blocks):
            blocks_by_idx.append(None)
        else:
            blocks_by_idx.append(list(blocks))

    # ---------- 1) 逐张压缩 ----------
    for blocks in blocks_by_idx:
        if not blocks:
            continue
        for i, block in enumerate(blocks):
            if not _media_mime(block).startswith("image/"):
                continue
            compressed = await asyncio.to_thread(
                _compress_image_block,
                block,
                max_px=conf["max_px"],
                target_bytes=conf["max_bytes"],
            )
            if compressed is not None:
                blocks[i] = compressed

    # ---------- 2) 总量预算：从最旧一端 offload ----------
    total_bytes = 0
    total_images = 0
    for blocks in blocks_by_idx:
        if not blocks:
            continue
        for block in blocks:
            if _media_payload(block) is None:
                continue
            total_bytes += _payload_bytes(block)
            if _media_mime(block).startswith("image/"):
                total_images += 1

    over_bytes = conf["budget_bytes"] > 0 and total_bytes > conf["budget_bytes"]
    over_images = conf["budget_images"] > 0 and total_images > conf["budget_images"]
    if over_bytes or over_images:
        # 阶梯式高水位：一次多放掉一个 offload 额度，避免下一张图又触发改写
        target_bytes = (
            max(0, conf["budget_bytes"] - conf["offload_bytes"])
            if over_bytes
            else 0
        )
        target_images = conf["budget_images"] if over_images else 0
        kept_bytes = 0
        kept_images = 0
        first_media = True

        for idx in range(len(messages) - 1, -1, -1):
            blocks = blocks_by_idx[idx]
            if not blocks:
                continue
            for i in range(len(blocks) - 1, -1, -1):
                block = blocks[i]
                if _media_payload(block) is None:
                    continue

                size = _payload_bytes(block)
                is_image = _media_mime(block).startswith("image/")

                # 最新的一块无论如何保留：即便它自己就超预算，也不能把刚发来的图丢掉
                drop_for_bytes = (
                    over_bytes and kept_bytes + size > target_bytes
                )
                drop_for_images = (
                    over_images
                    and is_image
                    and kept_images + 1 > target_images
                )
                if not first_media and (drop_for_bytes or drop_for_images):
                    blocks[i] = _elide_block(block, messages[idx])
                    continue

                first_media = False
                kept_bytes += size
                if is_image:
                    kept_images += 1

    # ---------- 3) 写回变化 ----------
    updated: list = []
    for idx, message in enumerate(messages):
        blocks = blocks_by_idx[idx]
        if blocks is None:
            continue
        original = _blocks_of(message)
        if blocks == original:
            continue
        # 同 id 覆盖才能替换 state 里的原消息；缺 id 的消息（旧 checkpoint 里的历史）
        # 必须就地补上，否则 LangGraph 会把这份副本当成新消息追加，反而多一条
        if not getattr(message, "id", None):
            message.id = uuid.uuid4().hex
        updated.append(message.model_copy(update={"content": blocks}))

    if not updated:
        return None

    logger.info(
        "媒体守卫：处理 %d 条消息（图片 %d 张，内联 %.1fMB；预算 %dKB/%d 张，offload 阶梯 %dKB）",
        len(updated),
        total_images,
        total_bytes / 1024 / 1024,
        conf["budget_bytes"] // 1024,
        conf["budget_images"],
        conf["offload_bytes"] // 1024,
    )
    return {"messages": updated}


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
        "当主人需求命中某个技能的触发场景时，先用 read_file 读它的 SKILL.md"
        "（给 limit=1000，默认 100 行通常不够），再按里面的步骤执行；"
        "技能自带的脚本用绝对路径直接跑（技能库是独立目录，通常不在工作区内，"
        "不要用相对路径猜；命令默认在工作区根目录执行，不用 cd）：",
    ]
    for idx, sk in enumerate(skills, 1):
        desc = sk["description"] or "无描述"
        entry = os.path.join(SKILLS_ROOT, sk["name"], "SKILL.md").replace("\\", "/")
        lines.append(
            f"- 第{idx}个技能 | 名称：{sk['name']} | 描述：{desc}"
            f" | 入口：{entry}"
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
