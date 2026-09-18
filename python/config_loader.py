# -*- coding: utf-8 -*-
"""
运行时配置加载器。

配置优先级（低 -> 高）：
  内置默认值 -> 环境变量（开发调试 fallback） -> config.user.json（Electron 设置页写入）

文件路径由启动参数 --config 传入；缺省时退化为环境变量 SASSY_CAT_CONFIG 指向的文件。
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

# ---------- 内置默认值（与 electron 模板 config.json 中的 agent/server 段对应） ----------
DEFAULTS = {
    "llm": {
        "activeProfile": "default",
        "profiles": {
            "default": {
                "label": "默认",
                "provider": "openai",
                "baseUrl": "",
                "apiKey": "",
                "model": "",
                "extraParams": {},
            }
        },
    },
    "agent": {
        "activeProfile": "default",
        "profiles": {
            "default": {
                "persona": "",  # 空字符串表示使用内置默认人设（见 agent/prompts.py）
                "memoryWindow": 50,
                "recursionLimit": 100,  # langgraph 单轮最大递归步数（见 agent/runner.py）
            }
        },
        # 保留顶层字段作为兼容旧配置的 fallback
        "skillsEnabled": True,
        "maxToolRounds": 10,
        "tavilyApiKey": "",  # Tavily 网络搜索 API Key
        "ocrEngine": "markitdown",  # agent对话时的ocr引擎，默认markitdown(快速),可选docling(更精细可识图)
        # 高危工具人工确认策略：true=执行前打断等待用户确认，false=直接放行
        # 见 agent/engine.py（构建 deep agent 时作为 interrupt_on 传入）
        "interruptOn": {
            "run_command": True,
            "write_file": True,
            "edit_file": True,
            "delete": True,
        },
    },
    "server": {
        "wsPort": 8790,
        "host": "127.0.0.1",
    },
    "pet": {
        "idleReminder": {
            "enabled": True,
            "thresholdMinutes": 30,
            "quietPeriodMinutes": 10,
        },
        "reminders": {
            "pollIntervalSeconds": 5,  # 提醒轮询间隔（秒），3~30，默认 5
            "bubbleDurationMs": 8000,  # 提醒气泡显示时长（毫秒），3000~30000，默认 8000
        },
    },
    "rag": {
        "autoEmbedding": True,  # 普通聊天上传文件自动embedding到默认知识库（异步）
        "embeddingModel": {
            "type": "local",  # 使用本地embedding model, 还可选remote（OpenAIEmbeddings）
            "model": "BAAI/bge-small-zh-v1.5",  # embedding model name
            "baseUrl": "",  # 本地向量模型无
            "apiKey": "",  # 本地向量模型无
            "downloaded": False,  # 本地模式：是否已通过智能下载完成模型下载（True 后设置页不再显示下载按钮）
            "localPath": "",  # 本地模式：下载完成后模型的本地目录
        },
        "ocrEngine": "docling"  # rag库维护上传文本使用的ocr引擎
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """递归合并 dict：override 优先，返回新 dict"""
    result = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _env_overrides(cfg: dict) -> dict:
    """环境变量 fallback（开发调试用），仅覆盖默认 profile 的连接参数"""
    profile = cfg["llm"]["profiles"]["default"] = dict(
        cfg["llm"]["profiles"]["default"]
    )
    if os.getenv("LLM_BASE_URL"):
        profile["baseUrl"] = os.environ["LLM_BASE_URL"]
    if os.getenv("LLM_API_KEY"):
        profile["apiKey"] = os.environ["LLM_API_KEY"]
    if os.getenv("LLM_MODEL_NAME"):
        profile["model"] = os.environ["LLM_MODEL_NAME"]
    if os.getenv("TAVILY_API_KEY"):
        cfg["agent"]["tavilyApiKey"] = os.environ["TAVILY_API_KEY"]
    return cfg


class AppConfig:
    """点路径访问的配置对象，如 cfg.get('llm.activeProfile')"""

    def __init__(self, data: dict):
        self._data = data

    def get(self, dotted: str, default=None):
        node = self._data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def raw(self) -> dict:
        return self._data

    def active_llm_profile(self) -> dict:
        name = self.get("llm.activeProfile", "default")
        profiles = self.get("llm.profiles", {}) or {}
        return profiles.get(name) or profiles.get("default") or {}

    def active_agent_profile(self) -> dict:
        """获取当前 active agent profile"""
        name = self.get("agent.activeProfile", "default")
        profiles = self.get("agent.profiles", {}) or {}
        return profiles.get(name) or profiles.get("default") or {}

    def active_agent_config(self) -> dict:
        """从当前 active agent profile 中读取配置（persona/memoryWindow/recursionLimit），
        若 profile 中未设置则回退到顶层 agent 段（兼容旧配置）"""
        profile = self.active_agent_profile()
        persona = profile.get("persona")
        if persona is None:
            persona = self.get("agent.persona", "")
        memory_window = profile.get("memoryWindow")
        if memory_window is None:
            memory_window = self.get("agent.memoryWindow", 50)
        recursion_limit = profile.get("recursionLimit")
        if recursion_limit is None:
            recursion_limit = self.get("agent.recursionLimit", 100)
        return {
            "persona": persona,
            "memoryWindow": memory_window,
            "recursionLimit": recursion_limit,
        }


_current: AppConfig = AppConfig(json.loads(json.dumps(DEFAULTS)))
_config_path: str | None = None


def load_config(path: str | None) -> AppConfig:
    """加载用户配置文件并与默认值合并，结果作为全局当前配置"""
    global _current, _config_path
    _config_path = path
    data = json.loads(json.dumps(DEFAULTS))  # deep copy defaults
    if path and os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
            data = _deep_merge(data, user_cfg)
            logger.info(f"已加载用户配置: {path}")
        except Exception as e:
            logger.warning(f"用户配置解析失败，使用默认值: {e}")
    else:
        logger.info("未提供或未找到用户配置文件，使用默认值 + 环境变量")
    data = _env_overrides(data)
    _current = AppConfig(data)
    return _current


def reload_config() -> AppConfig:
    """重新从磁盘读取配置文件并更新全局配置（热重载）"""
    if _config_path is None:
        logger.warning("reload_config: 未记录配置文件路径，跳过")
        return _current
    return load_config(_config_path)


def current() -> AppConfig:
    return _current
