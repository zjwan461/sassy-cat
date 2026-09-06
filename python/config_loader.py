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
                "baseUrl": "",
                "apiKey": "",
                "model": "",
                "extraParams": {},
            }
        },
    },
    "agent": {
        "persona": "",           # 空字符串表示使用内置默认人设（见 agent/prompts.py）
        "skillsEnabled": True,
        "maxToolRounds": 10,
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
    profile = cfg["llm"]["profiles"]["default"] = dict(cfg["llm"]["profiles"]["default"])
    if os.getenv("LLM_BASE_URL"):
        profile["baseUrl"] = os.environ["LLM_BASE_URL"]
    if os.getenv("LLM_API_KEY"):
        profile["apiKey"] = os.environ["LLM_API_KEY"]
    if os.getenv("LLM_MODEL_NAME"):
        profile["model"] = os.environ["LLM_MODEL_NAME"]
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


_current: AppConfig = AppConfig(json.loads(json.dumps(DEFAULTS)))


def load_config(path: str | None) -> AppConfig:
    """加载用户配置文件并与默认值合并，结果作为全局当前配置"""
    global _current
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


def current() -> AppConfig:
    return _current
