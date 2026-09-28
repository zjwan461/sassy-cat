# -*- coding: utf-8 -*-
"""临时探测：dsh 子代理「顶层 dsh 配置块」的读取链路与热重载失效（用完可删）。

覆盖：
1) 无用户配置：默认复用主 Agent LLM、内置系统提示词、maxTokens=131072、不传 reasoningEffort；
2) dsh.useMainLlm 缺省/true 复用主 Agent 激活 profile；false 时改用 dsh.llm 独立连接；
3) 顶层 dsh.maxTokens / dsh.reasoningEffort 生效；
4) 旧位置只读回退（llm.*.extraParams.*、agent.profiles.*.dshSystemPrompt、顶层 agent.dshSystemPrompt）；
5) 非法值降级（reasoningEffort 白名单外 -> None；maxTokens 非正整数 -> 131072）；
6) invalidate_harness() 之后 _get_harness() 会重建（monkeypatch build_harness 计数）。

为避免污染真实用户数据目录，启动时把 SASSY_CAT_DATA_DIR 指到临时目录，
并清掉可能存在的 LLM_* 环境变量（否则 config_loader 的环境变量回退会干扰断言）。
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "python"))

# 隔离真实环境：临时数据目录 + 清掉开发调试用的覆盖变量
os.environ["SASSY_CAT_DATA_DIR"] = tempfile.mkdtemp(prefix="dsh-probe-data-")
for _key in (
    "SASSY_CAT_CONFIG",
    "LLM_BASE_URL",
    "LLM_API_KEY",
    "LLM_MODEL_NAME",
    "TAVILY_API_KEY",
):
    os.environ.pop(_key, None)

from agent.tools.dsh import dsh_invoker  # noqa: E402

FAILURES: list[str] = []


def check(label: str, actual, expected) -> None:
    ok = actual == expected
    tail = "" if ok else f" != 期望 {expected!r}"
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}: {actual!r}{tail}")
    if not ok:
        FAILURES.append(label)


def load(cfg: dict) -> dict:
    """把 cfg 写成临时 config.user.json 后走一遍 load_llm_settings。"""
    fd, path = tempfile.mkstemp(suffix=".json", prefix="dsh-cfg-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False)
    try:
        return dsh_invoker.load_llm_settings(path)
    finally:
        os.remove(path)


def expect_default_prompt() -> str:
    return dsh_invoker.DEFAULT_SYSTEM_PROMPT.strip().replace(
        "{shell_guidance}", dsh_invoker.shell_guidance()
    )


def test_defaults() -> None:
    print("=== 1) 无用户配置：默认复用主 Agent LLM ===")
    s = load({})
    check("base_url 回退", s["base_url"], dsh_invoker.FALLBACK_BASE_URL)
    check("api_key 回退", s["api_key"], dsh_invoker.FALLBACK_API_KEY)
    check("model 回退", s["model"], dsh_invoker.FALLBACK_MODEL)
    check("max_tokens 默认", s["max_tokens"], dsh_invoker.FALLBACK_MAX_TOKENS)
    check("reasoning_effort 默认不传", s["reasoning_effort"], None)
    check("system_prompt 用内置默认", s["system_prompt"], expect_default_prompt())


def test_use_main_llm() -> None:
    print("=== 2) useMainLlm 开关 ===")
    base = {
        "llm": {
            "profiles": {
                "default": {
                    "baseUrl": "http://main:1234/v1",
                    "apiKey": "sk-main",
                    "model": "main-model",
                }
            }
        },
        "dsh": {
            "llm": {
                "baseUrl": "http://dsh:9999/v1",
                "apiKey": "sk-dsh",
                "model": "dsh-model",
            }
        },
    }
    s = load(base)
    check(
        "useMainLlm 缺省 -> 复用主 Agent profile",
        (s["base_url"], s["api_key"], s["model"]),
        ("http://main:1234/v1", "sk-main", "main-model"),
    )

    independent = json.loads(json.dumps(base))
    independent["dsh"]["useMainLlm"] = False
    s2 = load(independent)
    check(
        "useMainLlm=false -> 独立连接",
        (s2["base_url"], s2["api_key"], s2["model"]),
        ("http://dsh:9999/v1", "sk-dsh", "dsh-model"),
    )

    explicit_true = json.loads(json.dumps(base))
    explicit_true["dsh"]["useMainLlm"] = True
    check("useMainLlm=true -> 复用主 Agent profile", load(explicit_true)["model"], "main-model")


def test_top_level_params() -> None:
    print("=== 3) 顶层 dsh.maxTokens / dsh.reasoningEffort ===")
    s = load({"dsh": {"maxTokens": 4096, "reasoningEffort": "high"}})
    check("max_tokens 生效", s["max_tokens"], 4096)
    check("reasoning_effort 生效", s["reasoning_effort"], "high")


def test_legacy_fallbacks() -> None:
    print("=== 4) 旧位置只读回退 ===")
    s = load(
        {
            "llm": {
                "profiles": {
                    "default": {"extraParams": {"maxTokens": 2048, "reasoningEffort": "low"}}
                }
            },
            "agent": {"profiles": {"default": {"dshSystemPrompt": "旧 profile 提示词"}}},
        }
    )
    check("max_tokens 回退 extraParams", s["max_tokens"], 2048)
    check("reasoning_effort 回退 extraParams", s["reasoning_effort"], "low")
    check("system_prompt 回退 agent profile", s["system_prompt"], "旧 profile 提示词")

    check(
        "system_prompt 回退顶层 agent.dshSystemPrompt",
        load({"agent": {"dshSystemPrompt": "旧顶层提示词"}})["system_prompt"],
        "旧顶层提示词",
    )

    # 新位置优先于旧位置
    priority = {
        "dsh": {"maxTokens": 8192, "reasoningEffort": "max", "systemPrompt": "新提示词"},
        "llm": {"profiles": {"default": {"extraParams": {"maxTokens": 1, "reasoningEffort": "off"}}}},
        "agent": {"profiles": {"default": {"dshSystemPrompt": "旧提示词"}}},
    }
    sp = load(priority)
    check("新位置优先：max_tokens", sp["max_tokens"], 8192)
    check("新位置优先：reasoning_effort", sp["reasoning_effort"], "max")
    check("新位置优先：system_prompt", sp["system_prompt"], "新提示词")


def test_invalid_values() -> None:
    print("=== 5) 非法值降级 ===")
    s = load({"dsh": {"maxTokens": "abc", "reasoningEffort": "ultra"}})
    check("maxTokens 非数字 -> 默认", s["max_tokens"], dsh_invoker.FALLBACK_MAX_TOKENS)
    check("reasoningEffort 白名单外 -> None", s["reasoning_effort"], None)

    s2 = load({"dsh": {"maxTokens": -5}})
    check("maxTokens 负值 -> 默认", s2["max_tokens"], dsh_invoker.FALLBACK_MAX_TOKENS)

    s3 = load({"dsh": {"maxTokens": "32768"}})
    check("maxTokens 数字字符串 -> 取整", s3["max_tokens"], 32768)


def test_harness_invalidation() -> None:
    print("=== 6) invalidate_harness() 触发重建 ===")
    try:
        from agent.tools import subagent_tool
    except Exception as exc:  # pragma: no cover - 未安装 dsh/langchain 时跳过
        print(f"  [SKIP] 无法导入 subagent_tool：{exc}")
        return

    calls = {"n": 0}

    class FakeHarness:
        def close(self) -> None:
            pass

    def fake_build(settings):
        calls["n"] += 1
        return FakeHarness()

    original = subagent_tool.dsh_invoker.build_harness
    subagent_tool.dsh_invoker.build_harness = fake_build
    try:
        subagent_tool._HARNESS = None
        subagent_tool._HARNESS_STALE = False

        subagent_tool._get_harness()
        check("首次获取 -> 构建 1 次", calls["n"], 1)
        subagent_tool._get_harness()
        check("未变更 -> 不重建", calls["n"], 1)
        subagent_tool.invalidate_harness()
        check("invalidate 置脏", subagent_tool._HARNESS_STALE, True)
        subagent_tool._get_harness()
        check("invalidate 后 -> 重建", calls["n"], 2)
        check("重建后清脏", subagent_tool._HARNESS_STALE, False)
    finally:
        subagent_tool.dsh_invoker.build_harness = original
        subagent_tool._HARNESS = None
        subagent_tool._HARNESS_STALE = False


def main() -> None:
    for fn in (
        test_defaults,
        test_use_main_llm,
        test_top_level_params,
        test_legacy_fallbacks,
        test_invalid_values,
        test_harness_invalidation,
    ):
        fn()
        print()
    if FAILURES:
        print(f"[FAILED] {len(FAILURES)} 项断言失败: {FAILURES}")
        sys.exit(1)
    print("[OK] 全部断言通过")


main()