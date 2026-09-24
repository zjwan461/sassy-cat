#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通过 dsh(DeepSeek Harness)Python SDK 跑一轮对话的最小可运行示例。

LLM 连接参数不写死在本文件：model / apiKey / baseUrl 全部从项目运行配置
（config.user.json 的 llm.profiles.<activeProfile> 段）读取，与 agent/llms.py
里 langchain 走的是同一份配置，避免两处连接参数漂移。

为什么路由名固定是 deepseek-official
------------------------------------
sdk-minimal profile 的插件树里只挂了一个 LLM 适配器
`@deepseek-ai/dsh-llm-deepseek`，它注册的路由名固定为 `deepseek-official`
（再为同一路由注册别的适配器会以 DUPLICATE_ADAPTER 失败）。按该适配器官方
文档，它同时支持 DeepSeek 官方 API 与**任意 OpenAI 兼容网关**（vLLM /
llama.cpp / LM Studio / 各类中转）：端点由 baseURL 决定，模型 id 原样透传到
wire，所以自建服务不需要新插件，把 baseUrl 指过去即可。
（若将来要同时路由多家 provider，可另加 `@deepseek-ai/dsh-llm-pi-ai` 行到
patch 文件，用它的 providers 字典声明自定义路由名，SDK 的 provider 参数随之传
那个路由名。）

base_url / api_key 的传递链路
----------------------------
DeepSeekHarness(base_url=..., api_key=...) -> 子进程环境变量
DEEPSEEK_BASE_URL / DEEPSEEK_API_KEY -> dsh-llm-deepseek 的端点解析：
    config.baseURL ?? $DEEPSEEK_BASE_URL ?? https://api.deepseek.com
即环境变量优先于 profile 里写死的 baseURL，且是"每个请求解析"，换地址不需要
改 patch 文件、不需要重启。
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Any

# 让 `python python/agent/tools/dsh/dsh_invoker.py` 和
# `python -m agent.tools.dsh.dsh_invoker` 两种跑法都能 import 到顶层模块
# （项目里 config_loader / paths / agent 都以 python/ 为根）
_PYTHON_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _PYTHON_ROOT not in sys.path:
    sys.path.insert(0, _PYTHON_ROOT)

import config_loader  # noqa: E402
import paths  # noqa: E402
from deepseek_harness import DeepSeekHarness  # noqa: E402

from agent.constant import WORK_DIR  # noqa: E402

logger = logging.getLogger(__name__)

# dsh 侧路由名，见模块 docstring：固定值，不随项目 config 的 provider 字段变化
# （项目里的 provider 只决定用哪个 langchain 客户端，不是 dsh 的路由名）
DSH_ROUTE = "deepseek-official"
DSH_PROFILE = "sdk-minimal"

# 兜底值与 agent/llms.py 保持一致，避免"项目里能聊、dsh 起不来"
FALLBACK_BASE_URL = "http://localhost:8080/v1"
FALLBACK_API_KEY = "sk-xxx"
FALLBACK_MODEL = "Qwen3.6-35B"
# 输出上限必须显式给：llm-deepseek 适配器默认 256000，而 DashScope 的 qwen 系
# 只接受 [1, 131072]，不给会直接被 400
# InternalError.Algo.InvalidParameter 挡下来（实测）。可用
# llm.profiles.<name>.extraParams.maxTokens 覆盖。
FALLBACK_MAX_TOKENS = 131072

WORKSPACE = os.path.join(WORK_DIR, ".dsh", "workspace")
DSH_HOME = os.path.join(WORK_DIR, ".dsh", "home")
PATCH_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "editor.patch.yml")


def resolve_config_path(explicit: str | None = None) -> str:
    """按 main.py 的口径定位 config.user.json：显式参数 -> 环境变量 -> userData。

    paths.data_path 未 init 时会惰性走兜底目录（Windows 为 %APPDATA%\\sassy-cat），
    与 Electron 主进程 app.getPath('userData') 指向同一处。
    """
    if explicit:
        return explicit
    return os.getenv("SASSY_CAT_CONFIG") or paths.data_path("config.user.json")


def load_llm_settings(config_path: str) -> dict[str, Any]:
    """读取 active LLM profile，翻译成 DeepSeekHarness 的连接参数。"""
    cfg = config_loader.load_config(config_path)
    profile = cfg.active_llm_profile() or {}
    extra = profile.get("extraParams") or {}

    base_url = (profile.get("baseUrl") or "").strip() or FALLBACK_BASE_URL
    api_key = (profile.get("apiKey") or "").strip() or FALLBACK_API_KEY
    model = (profile.get("model") or "").strip() or FALLBACK_MODEL

    # initialize 只接受 positive safe integer：配置里写成 "131072" 会被 schema 拒掉
    raw_max_tokens = extra.get("maxTokens")
    max_tokens = (
        int(raw_max_tokens) if raw_max_tokens is not None else FALLBACK_MAX_TOKENS
    )

    # reasoningEffort 是适配器自有的标识符（deepseek-official 支持 off/low/high/max），
    # 项目配置里没有就不传，让适配器默认值生效
    reasoning_effort = extra.get("reasoningEffort") or None

    logger.info(
        "dsh LLM: route=%s model=%s baseUrl=%s maxTokens=%s",
        DSH_ROUTE,
        model,
        base_url,
        max_tokens,
    )
    return {
        "base_url": base_url,
        "api_key": api_key,
        "model": model,
        "max_tokens": max_tokens,
        "reasoning_effort": reasoning_effort,
    }


def build_harness(settings: dict[str, Any]) -> DeepSeekHarness:
    """组装 harness。所有取值都来自上面的配置读取，不在本函数里写死连接参数。"""
    os.makedirs(WORKSPACE, exist_ok=True)
    os.makedirs(DSH_HOME, exist_ok=True)

    return DeepSeekHarness(
        provider=DSH_ROUTE,
        model=settings["model"],
        reasoning_effort=settings["reasoning_effort"],
        max_tokens=settings["max_tokens"],
        cwd=WORKSPACE,
        dsh_home=DSH_HOME,
        profile=DSH_PROFILE,
        # 必须是 tuple：DeepSeekHarnessConfig.patches 是 tuple[str, ...]，
        # 传裸字符串不会报类型错，而是被逐字符迭代成几十个
        # `--patch <单个字符 resolved 后的绝对路径>`，dsh 在第一个字符上就
        # failed to read overlay 崩掉
        patches=(PATCH_FILE,),
        # client 侧是 os.environ.copy() 再 update，所以这里只需增量注入
        env={"DSH_HOME": DSH_HOME},
        # 以下两项由 SDK 写成 DEEPSEEK_BASE_URL / DEEPSEEK_API_KEY 传给 dsh 子进程
        base_url=settings["base_url"],
        api_key=settings["api_key"],
        initialize_timeout_seconds=30.0,
        request_timeout_seconds=None,
    )


def notification_sink(notification: Any) -> None:
    print(notification)


def main() -> None:
    parser = argparse.ArgumentParser(description="dsh(DeepSeek Harness)单轮调用示例")
    parser.add_argument(
        "--config",
        default=None,
        help="config.user.json 路径（缺省：$SASSY_CAT_CONFIG，再到 userData）",
    )
    parser.add_argument("--prompt", default="hi", help="单轮提示词")
    parser.add_argument(
        "--session-id",
        default=None,
        help="会话 id；缺省由 SDK 自动生成 session-<uuid>。dsh 的会话是持久化的"
        "（$DSH_HOME 下 JSONL），复用已存在的 id 会报 session already exists",
    )
    args = parser.parse_args()

    settings = load_llm_settings(resolve_config_path(args.config))

    # with 保证子进程被回收（close 会发 shutdown 并等待，随后断流）
    harness = build_harness(settings)
    with harness:
        result = harness.run(
            args.prompt,
            session_id=args.session_id,
            on_notification=notification_sink,
        )
    print(result)


if __name__ == "__main__":
    main()
