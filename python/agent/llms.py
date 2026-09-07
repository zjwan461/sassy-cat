from langchain_openai import ChatOpenAI
from langchain_deepseek import ChatDeepSeek
import logging

logger = logging.getLogger(__name__)


def build_chat_llm(profile_cfg: dict):
    """由配置构建 LLM 实例。根据 provider 字段选择 OpenAI 或 DeepSeek。

    profile_cfg 结构（来自 config.user.json 的 llm.profiles.*）：
      { baseUrl, apiKey, model, provider, extraParams }

    provider 可选值：
      - "openai" (默认): 使用 ChatOpenAI，reasoning 放在 content 中
      - "deepseek": 使用 ChatDeepSeek，reasoning 放在 reasoning_content 中
    """
    provider = profile_cfg.get("provider") or "openai"

    if provider == "deepseek":
        return build_ds_chat_llm(profile_cfg)
    else:
        return build_openai_chat_llm(profile_cfg)


def build_openai_chat_llm(profile_cfg: dict):
    # 默认使用 OpenAI 兼容模式
    logger.info("构建provider=openai类型的llm")
    extra = dict(profile_cfg.get("extraParams") or {})
    return ChatOpenAI(
        base_url=profile_cfg.get("baseUrl") or "http://localhost:8080/v1",
        api_key=profile_cfg.get("apiKey") or "sk-xxx",
        model=profile_cfg.get("model") or "Qwen3.6-35B",
        extra_body=extra,
    )


def build_ds_chat_llm(profile_cfg: dict):
    """由配置构建 ChatDeepSeek实例。reasonging放在reasoning_content中。

    profile_cfg 结构（来自 config.user.json 的 llm.profiles.*）：
     { baseUrl, apiKey, model, extraParams }
    """
    logger.info("构建provider=deepseek类型的llm")
    extra = dict(profile_cfg.get("extraParams") or {})
    return ChatDeepSeek(
        base_url=profile_cfg.get("baseUrl") or "http://localhost:8080/v1",
        api_key=profile_cfg.get("apiKey") or "sk-xxx",
        model=profile_cfg.get("model") or "Qwen3.6-35B",
        extra_body=extra,
    )
