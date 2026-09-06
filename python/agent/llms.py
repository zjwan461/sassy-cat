from langchain_openai import ChatOpenAI


def build_chat_llm(profile_cfg: dict):
    """由配置构建 ChatOpenAI 实例。

    profile_cfg 结构（来自 config.user.json 的 llm.profiles.*）：
      { baseUrl, apiKey, model, extraParams }
    """
    extra = dict(profile_cfg.get("extraParams") or {})
    return ChatOpenAI(
        base_url=profile_cfg.get("baseUrl") or "http://localhost:8080/v1",
        api_key=profile_cfg.get("apiKey") or "sk-xxx",
        model=profile_cfg.get("model") or "Qwen3.6-35B",
        **extra,
    )
