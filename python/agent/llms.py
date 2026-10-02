from langchain_openai import ChatOpenAI
from langchain_deepseek import ChatDeepSeek
import logging

logger = logging.getLogger(__name__)


def build_chat_llm(profile_cfg: dict):
    """由配置构建 LLM 实例。根据 provider 字段选择 OpenAI 或 DeepSeek。

    profile_cfg 结构（来自 config.user.json 的 llm.profiles.*）：
      { baseUrl, apiKey, model, provider, temperature, contextWindow, extraParams }

    provider 可选值：
      - "openai" (默认): 使用 ChatOpenAI，reasoning 放在 content 中
      - "deepseek": 使用 ChatDeepSeek，reasoning 放在 reasoning_content 中
    """
    provider = profile_cfg.get("provider") or "openai"

    if provider == "deepseek":
        return build_ds_chat_llm(profile_cfg)
    else:
        return build_openai_chat_llm(profile_cfg)


def _resolve_temperature(profile_cfg: dict, default: float = 0.7) -> float:
    """解析采样温度（llm.profiles.<name>.temperature）。

    - 缺失 / 空串 -> 默认值 0.7（与 config_loader.DEFAULTS 一致）
    - 非法值 -> 告警并回退默认值
    - 合法值 -> 夹到 [0, 2] 区间，避免服务商因越界报错

    注意：温度是浮点数，不能用 int() 解析（int(0.7) 会被截断成 0）。
    """
    raw = profile_cfg.get("temperature")
    if raw is None or raw == "":
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        logger.warning("temperature=%r 无法解析为数字，回退默认值 %s", raw, default)
        return default
    return min(2.0, max(0.0, value))


def build_openai_chat_llm(profile_cfg: dict):
    # 默认使用 OpenAI 兼容模式
    logger.info("构建provider=openai类型的llm")
    extra = dict(profile_cfg.get("extraParams") or {})
    return ChatOpenAI(
        base_url=profile_cfg.get("baseUrl") or "http://localhost:8080/v1",
        api_key=profile_cfg.get("apiKey") or "sk-xxx",
        model=profile_cfg.get("model") or "Qwen3.6-35B",
        temperature=_resolve_temperature(profile_cfg),
        extra_body=extra,
    )


def build_ds_chat_llm(profile_cfg: dict):
    """由配置构建 ChatDeepSeek实例。reasonging放在reasoning_content中。

    profile_cfg 结构（来自 config.user.json 的 llm.profiles.*）：
     { baseUrl, apiKey, model, temperature, extraParams }
    """
    logger.info("构建provider=deepseek类型的llm")
    extra = dict(profile_cfg.get("extraParams") or {})
    return ChatDeepSeek(
        base_url=profile_cfg.get("baseUrl") or "http://localhost:8080/v1",
        api_key=profile_cfg.get("apiKey") or "sk-xxx",
        model=profile_cfg.get("model") or "Qwen3.6-35B",
        temperature=_resolve_temperature(profile_cfg),
        extra_body=extra,
    )


def simple_blocking_call(llm, prompt: str) -> str | None:
    result = llm.invoke(prompt)
    if getattr(result, "content"):
        return result.content
    else:
        return None


async def simple_streaming_call(llm, prompt: str):
    """纯流式调用：逐块产出增量文本（str），不使用任何 Agent/工具能力。

    与 simple_blocking_call 对等的流式版本，基于 llm.astream。
    reasoning 内容（reasoning_content）不产出，只输出正式回复正文。
    """
    async for chunk in llm.astream(prompt):
        text = chunk.content if isinstance(chunk.content, str) else ""
        # 兼容多模态 content 列表形式（部分 provider 返回 [{type:text,...}]）
        if not text and isinstance(chunk.content, list):
            text = "".join(
                p.get("text", "") for p in chunk.content
                if isinstance(p, dict) and p.get("type") == "text"
            )
        if text:
            yield text
