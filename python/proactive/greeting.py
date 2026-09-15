# -*- coding: utf-8 -*-
"""
桌宠每日首次加载打招呼（招呼 + 近期待办提醒）。

触发：pet 客户端 WS 连上 Python 服务时由 server/ws_agent 调用 maybe_greet()。
去重：按自然日判定，lastGreetingDate 持久化到数据目录 greeting_state.json，
      进程重启 / 多窗口重连当天都不会重复打招呼。
文案：读取未完成提醒（agent.reminders.list_reminders status=active），
      与「当前人设 + 打招呼指令」一起构造提示词，直接调 LLM 流式生成
      （agent/llms.simple_streaming_call，不带任何 Agent 工具能力），
      最终效果 = 打招呼 + 提醒今天/明天/近期的待办事项；
      未配置 LLM（baseUrl/model 为空）、调用异常或超时，则回退内置
      hardcode 时段文案池随机选一条（有待办时追加硬编码待办提示行）。
展示：通过事件总线广播 greeting.delta / greeting.completed，
      桌宠端复用既有气泡打字机逐字显示。
"""

import asyncio
import datetime as dt
import json
import logging
import random
import uuid

import config_loader
import paths
from agent.llms import build_chat_llm, simple_streaming_call
from agent.prompts import DEFAULT_PERSONA
from server import bus
from server.protocol import envelope
from agent.reminders import describe_repeat, list_reminders

logger = logging.getLogger(__name__)

# 连接后宽限等待（秒）：等 Electron setPort 可能引发的重连落定，避免半路打扰
GRACE_SECONDS = 3.0
# 等待进行中聊天轮次空闲的最长时间（秒），超时则放弃并回滚今日标记
BUSY_WAIT_TIMEOUT = 60.0
# LLM 单块流式读取超时（秒）
CHUNK_TIMEOUT = 8.0
# 整体生成超时（秒），防止长尾挂死
TOTAL_TIMEOUT = 45.0

_STATE_FILE = "greeting_state.json"

# 模块级并发保护：同一天内多 pet 连接（重连/多实例）只允许一个打招呼任务在跑
_inflight = False

# 未配置 LLM 或调用失败时的内置兜底文案：按时段随机
FALLBACK_POOL = {
    "morning": [
        "早上好喵～新的一天，本喵先到了，你才刚来？😾",
        "早安！昨晚睡得好吗？本喵可是早就精神了，哼。",
        "喵呜～早起的猫有鱼干，今天的任务就交给本喵把关吧！",
    ],
    "noon": [
        "中午啦，饭点到了喵！工作可以放一放，肚子不能亏待😾",
        "哼，本喵提醒你：该吃午饭了，饿晕在键盘上谁管你喵。",
    ],
    "afternoon": [
        "下午好喵～困了吧？摸一下本喵提提神，不收费。",
        "午后时光，本喵准许你伸个懒腰再继续卷，喵😾",
    ],
    "evening": [
        "晚上好喵！忙了一天，本喵勉强陪你歇一会儿吧。",
        "哼，终于到晚上啦，今天有本喵守着，算你运气好喵。",
    ],
    "night": [
        "这么晚还在忙？本喵都困了……你也不许熬夜，喵😾",
        "深夜了喵……早点休息，明天的事交给明天的本喵，晚安。",
    ],
}

_WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def _now() -> dt.datetime:
    return dt.datetime.now()


def _today() -> str:
    return _now().strftime("%Y-%m-%d")


def _time_slot() -> str:
    hour = _now().hour
    if 5 <= hour < 11:
        return "morning"
    if 11 <= hour < 14:
        return "noon"
    if 14 <= hour < 18:
        return "afternoon"
    if 18 <= hour < 23:
        return "evening"
    return "night"


def _slot_label() -> str:
    return {
        "morning": "早上",
        "noon": "中午",
        "afternoon": "下午",
        "evening": "晚上",
        "night": "深夜",
    }[_time_slot()]


def _state_path() -> str:
    return paths.data_path(_STATE_FILE)


def _read_state() -> dict:
    try:
        with open(_state_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.warning(f"读取打招呼状态文件失败（视为未打过招呼）: {e}")
        return {}


def _write_state(state: dict) -> None:
    """先占位写日期，防止并发/重连窗口期重复触发"""
    try:
        with open(_state_path(), "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
    except OSError as e:
        logger.warning(f"写入打招呼状态文件失败: {e}")


def _claim_today() -> bool:
    """原子占位：今日未打招呼则登记并返回 True；已打过/已被占则返回 False"""
    state = _read_state()
    if state.get("lastGreetingDate") == _today():
        return False
    state["lastGreetingDate"] = _today()
    _write_state(state)
    return True


def _release_claim() -> None:
    """放弃打招呼时回滚今日标记，让下次连接还能触发"""
    state = _read_state()
    if state.get("lastGreetingDate") == _today():
        state.pop("lastGreetingDate", None)
        _write_state(state)


def _llm_ready() -> bool:
    """判断 LLM 是否已配置：baseUrl / model 任一为空视为未配置"""
    profile = config_loader.current().active_llm_profile()
    return bool(profile.get("baseUrl")) and bool(profile.get("model"))


async def _emit(msg_id: str, text: str) -> None:
    """一次性完整推送（兜底文案、异常收尾共用）"""
    await bus.hub.publish_all(
        envelope("greeting.delta", {"msgId": msg_id, "text": text})
    )
    await bus.hub.publish_all(
        envelope("greeting.completed", {"msgId": msg_id, "text": text})
    )


async def _emit_fallback(msg_id: str) -> None:
    text = random.choice(FALLBACK_POOL[_time_slot()])
    logger.info(f"打招呼使用内置兜底文案: {text}")
    await _emit(msg_id, text)


async def _stream_greeting(msg_id: str) -> str | None:
    """流式调用 LLM 生成打招呼文案，逐块广播 greeting.delta。

    返回最终完整文本；未配置/异常/超时/空结果返回 None，由调用方回退兜底。
    """
    profile = config_loader.current().active_llm_profile()
    try:
        llm = build_chat_llm(profile)
        llm.extra_body = {"chat_template_kwargs": {"enable_thinking": False}}
    except Exception:
        logger.exception("构建打招呼 LLM 失败")
        return None

    try:
        prompt = await _build_prompt()
    except Exception:
        logger.exception("构造打招呼提示词失败")
        return None

    parts: list[str] = []
    agen = None
    try:
        agen = simple_streaming_call(llm, prompt).__aiter__()
        total_deadline = asyncio.get_event_loop().time() + TOTAL_TIMEOUT
        while True:
            remain = total_deadline - asyncio.get_event_loop().time()
            if remain <= 0:
                raise asyncio.TimeoutError("打招呼生成整体超时")
            try:
                piece = await asyncio.wait_for(
                    agen.__anext__(), timeout=min(CHUNK_TIMEOUT, remain)
                )
            except StopAsyncIteration:
                break
            parts.append(piece)
            await bus.hub.publish_all(
                envelope("greeting.delta", {"msgId": msg_id, "text": piece})
            )
    except asyncio.TimeoutError:
        logger.warning("打招呼 LLM 调用超时")
        if not parts:
            return None
        # 已流出部分内容：收尾保留已有文本，不回退兜底
    except Exception:
        logger.exception("打招呼 LLM 流式调用异常")
        if not parts:
            return None
    finally:
        # 超时/异常提前退出时显式关闭生成器，避免 provider 连接悬挂
        if agen is not None:
            try:
                await agen.aclose()
            except Exception:
                pass

    text = "".join(parts).strip()
    if not text:
        return None
    await bus.hub.publish_all(
        envelope("greeting.completed", {"msgId": msg_id, "text": text})
    )
    return text


# 提醒清单最多行数与"近期"窗口（天）。每个分组占 1 行标题 + N 行条目，
# 上限按"约 4 组 x 3 行"留足余量，避免分组标题挤掉后续汇总行
_MAX_REMINDER_LINES = 12
_NEAR_DAYS = 7


def _reminders_section() -> str:
    """把未完成提醒渲染成提示词附录（同步：sqlite store 阻塞 IO，调用方放 to_thread）。

    分类：已逾期 / 今天 / 明天 / 近期（7 天内）/ 更远期（只报数量）；
    无未完成提醒或读取失败时返回空串。
    """
    day_start = _now().replace(hour=0, minute=0, second=0, microsecond=0)
    ms_today_end = int((day_start + dt.timedelta(days=1)).timestamp() * 1000)
    ms_tomorrow_end = int((day_start + dt.timedelta(days=2)).timestamp() * 1000)
    ms_near_end = int(
        (day_start + dt.timedelta(days=1 + _NEAR_DAYS)).timestamp() * 1000
    )

    try:
        pending = [r for r in list_reminders(status="active") if r.get("next_at")]
    except Exception:
        logger.exception("读取未完成提醒失败（打招呼不带待办）")
        return ""

    overdue, today, tomorrow, near, later = [], [], [], [], []
    for rec in pending:
        nxt = rec["next_at"]
        if nxt <= _now().timestamp() * 1000:
            overdue.append(rec)
        elif nxt < ms_today_end:
            today.append(rec)
        elif nxt < ms_tomorrow_end:
            tomorrow.append(rec)
        elif nxt < ms_near_end:
            near.append(rec)
        else:
            later.append(rec)

    def line(rec: dict) -> str:
        when = dt.datetime.fromtimestamp(rec["next_at"] / 1000).strftime("%m-%d %H:%M")
        rep = describe_repeat(rec)
        return f"- [{when}｜{rep}] {rec.get('content') or '（无内容）'}"

    parts: list[str] = []
    for title, group in (
        ("已逾期", overdue),
        ("今天", today),
        ("明天", tomorrow),
        ("近期", near),
    ):
        if not group:
            continue
        parts.append(f"[{title}]")
        parts.extend(line(r) for r in group)
    if later:
        parts.append(f"[更远期] 另有 {len(later)} 条（7 天后）")
    if not parts:
        return ""

    # 控制总行数，超出截断并提示
    lines = parts[:_MAX_REMINDER_LINES]
    if len(parts) > _MAX_REMINDER_LINES:
        lines.append(
            f"- ……等共 {sum(map(len, (overdue, today, tomorrow, near)))} 条待办"
        )
    return "\n".join(lines)


async def _build_prompt() -> str:
    """当前人设 + 打招呼指令 + 未完成待办清单（不拼 RUNTIME_SKELETON，一次性生成无需工具约束）"""
    cfg = config_loader.current()
    persona = (cfg.active_agent_config().get("persona") or "").strip()
    if not persona:
        persona = DEFAULT_PERSONA.strip()
    now = _now()
    time_str = now.strftime("%Y-%m-%d %H:%M")
    weekday = _WEEKDAYS[now.weekday()]
    prompt = (
        f"{persona}\n\n---\n"
        f"现在是 {time_str}（{weekday}，{_slot_label()}），"
        "这是你今天第一次见到主人。请以上方人设的语气，向主人打一个开场招呼；"
        "若下方有未完成事项清单，再顺带温和提醒今天/明天/近期的待办"
        "（挑最要紧的两三条即可，不要逐条复读）。\n"
        "要求：只输出内容本身，不超过 100 个字；贴合当前时段；"
        "不要加引号、不要解释、不要输出多余前后缀。"
    )
    section = await asyncio.to_thread(_reminders_section)
    if section:
        prompt += "\n\n[主人未完成事项清单]\n" + section
    return prompt


async def _wait_until_idle() -> bool:
    """等待所有进行中的聊天轮次结束，避免打招呼气泡插进聊天打字机。

    返回 True 表示空闲可继续；超时返回 False。
    """
    # 惰性导入：ws_agent 顶层引用本模块，反向导入需放函数内防循环依赖
    from server import ws_agent

    waited = 0.0
    while ws_agent.has_running_turn():
        if waited >= BUSY_WAIT_TIMEOUT:
            return False
        await asyncio.sleep(2.0)
        waited += 2.0
    return True


async def maybe_greet() -> None:
    """pet 连接时调用：今日第一次则打招呼（幂等，非阻塞）"""
    global _inflight
    if _inflight:
        return
    _inflight = True
    try:
        if not _claim_today():
            return
        # 宽限期：桌宠初次连接后 Electron 可能因端口上报触发一次重连，稍候再判定
        await asyncio.sleep(GRACE_SECONDS)
        if not await _wait_until_idle():
            logger.info("聊天轮次持续进行中，放弃本次打招呼并回滚今日标记")
            _release_claim()
            return
        msg_id = "greet-" + uuid.uuid4().hex[:8]
        if not _llm_ready():
            logger.info("LLM 未配置，打招呼走内置兜底文案")
            await _emit_fallback(msg_id)
            return
        final = await _stream_greeting(msg_id)
        if final is None:
            await _emit_fallback(msg_id)
        else:
            logger.info(f"打招呼完成: {final[:40]}…")
    finally:
        _inflight = False
