#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通过 dsh(DeepSeek Harness)Python SDK 跑一轮对话的最小可运行示例。

LLM 连接参数不写死在本文件：默认复用主 Agent 当前激活的 LLM
（config.user.json 的 llm.profiles.<activeProfile> 段），与 agent/llms.py
里 langchain 走的是同一份配置，避免两处连接参数漂移；
设置页「dsh 子代理」可关闭该复用（dsh.useMainLlm=false），改读顶层 dsh.llm 的独立连接。

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

system prompt 的传递链路
-----------------------
DeepSeekHarness(env={"DSH_SYSTEM_PROMPT": ...}) -> 子进程环境变量 -> sdk-minimal
里 system-prompt 行的 personaPrefix：
    process.env.DSH_SYSTEM_PROMPT ?? 'You are a helpful software engineer assistant.'
该行 includeHarnessIdentity / includeRuntimeContext 都是 false，所以 dsh 的系统
消息基本就是这一段；不给这个变量，dsh 用它自己的英文默认值（实测 system/message
的内容就是那句英文）。

取值优先级：config.user.json 顶层 dsh.systemPrompt（设置页「dsh 子代理」卡片写入）
（兼容 agent.profiles.<active>.dshSystemPrompt / 顶层 agent.dshSystemPrompt）
-> DEFAULT_SYSTEM_PROMPT。

为什么不复用 agent/prompts.py 里主 agent 的 prompt（persona + RUNTIME_SKELETON）
------------------------------------------------------------------------------
那两段是给"能对话、有确认 UI、有全套项目工具"的主 agent 写的，dsh 三者都不具备：
  - 它要求调用 save_user_info / create_reminder / search_from_kb，而 dsh 的工具
    清单只有 shell / 编辑器 / present / glob / grep / todo（见 editor.patch.yml），
    硬套只会让它编造不存在的工具调用；
  - 它要求高危操作等用户确认，而这条链路是单向事件流，没有回执通道；
  - 它要求文件建在 /tmp、/data 这类虚拟路径，而 dsh 的工作目录是真实目录
    （runtime/.dsh/workspace），shell 必须用当前平台的原生路径。
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

# reasoningEffort 是 deepseek-official 适配器自有的标识符；白名单之外的值会被 dsh 的
# initialize schema 拒掉（整个子代理起不来），因此做过滤而不是原样透传
DSH_REASONING_EFFORTS = ("off", "low", "high", "max")

# 平台相关的 shell 指引：sdk-minimal 的 shell 工具本身就是平台二选一
# （--dump-config 里 persistent-bash 在 win32 上 disabled、persistent-pwsh 反之），
# 所以 Windows 上模型拿到的是 pwsh、macOS/Linux 上是 bash。写死任一种都会在另一个
# 平台上说错工具名与路径风格，因此拆出来按 sys.platform 选。
# 提示词里用 {shell_guidance} 占位，由 shell_guidance() 展开。
SHELL_GUIDANCE_WINDOWS = (
    "- 需要 shell 时注意这是真实的 PowerShell（pwsh）环境：当前目录用 `Get-Location` 看，"
    "路径用原生 Windows 写法（C:\\...），不要写成 Linux 风格的 /tmp、/data 这类虚拟路径。"
)
SHELL_GUIDANCE_POSIX = (
    "- 需要 shell 时注意这是真实的 bash 环境：当前目录用 `pwd` 看，"
    "路径用 POSIX 写法（/Users/... 或 /home/...），不要写成不存在的虚拟路径约定。"
)


def shell_guidance(platform: str | None = None) -> str:
    """按运行平台挑 shell 指引（默认取当前进程的 sys.platform）。"""
    current = platform or sys.platform
    return SHELL_GUIDANCE_WINDOWS if current.startswith("win") else SHELL_GUIDANCE_POSIX


# dsh 的系统提示词（DSH_SYSTEM_PROMPT）。它是"被委托的单向执行者"而不是聊天对象：
# 看不到主对话、没有确认 UI、工具集也不同，所以单独写一份，别复用主 agent 的
# persona/skeleton（理由见模块 docstring）。
# 注意：同一段文本作为默认值写在 resources/config.json 的 dsh.systemPrompt 里
# （设置页直接展示、可编辑），修改默认提示词时两处必须同步；配置非空时以配置为准。
DEFAULT_SYSTEM_PROMPT = """你是「优墨」的动手子代理，跑在一个独立的 dsh(DeepSeek Harness) 工作进程里。

你只拿到被委托的那一件事：调用方给出的任务描述就是你的全部上下文，不要指望能看到用户与优墨的对话历史。

任务规划（重要）：
- 硬规则：只要这件事**需要调用工具两次以上**，就属于多步任务，必须先把 todo_write 建好再动手。
  不要用"这题很机械""我几步就能写完"当理由跳过——多步且机械，正是最该用清单的场景。
- 只有"一次工具调用就能彻底做完"的事（一问一答、单条命令、单次读写单个文件）才不必建清单。
- 清单写 3~7 项，每项是一个能独立完成、能验证的动作，例如"创建 X 文件""运行 Y 并确认输出"。
- 第一步就建清单，这是默认动作：不需要调用方特地要求，也不要等"摸清情况之后"再补。
- 执行中每完成一项就立刻用 todo_write 更新状态（进行中/已完成），不要攒到最后一次性补写。
  注意它是**全量覆盖**：每次都要把整份清单（含未变的项）重新提交。
- 收尾时把所有项都标记为已完成再汇报；确实没做完的项要如实说明，不要留着不更新。
  "我先看看再说""边做边想下一步"都不算完成了规划。
工作方式：
- 先看清现状再动手：用 glob/grep 找文件、读文件确认内容，不要凭记忆猜目录结构或文件内容。
{shell_guidance}
- 写文件优先用 str_replace_editor（可分节追加），别把整份文件塞进一条 shell 命令——heredoc 与多行字符串的转义都很脆，还容易撞上单次响应的输出上限。
- 产出需要交给用户的文件时，用 present 声明。

边界：
- 没有交互界面：任何"等待用户确认/回答"的操作都不会有人回应。不要提问、不要等许可，直接用工具把任务做完。
- 只动与任务相关的文件，不要删除或覆盖无关内容。
- 完成后用一两句话汇报：做了什么、结果如何、有没有失败或没做完的部分。
"""
# 输出上限必须显式给：llm-deepseek 适配器默认 256000，而 DashScope 的 qwen 系
# 只接受 [1, 131072]，不给会直接被 400
# InternalError.Algo.InvalidParameter 挡下来（实测）。可用
# llm.profiles.<name>.extraParams.maxTokens 覆盖。
FALLBACK_MAX_TOKENS = 131072

WORKSPACE = os.path.join(WORK_DIR, ".dsh", "workspace")
DSH_HOME = os.path.join(WORK_DIR, ".dsh", "home")
PATCH_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "editor.patch.yml")
# 主 Agent 的技能库根目录（runtime/skills）。其结构 <name>/SKILL.md 与 dsh
# skill-filesystem 的 root 约定一致，因此可直接作为一个 customSkillDir 挂给 dsh，
# 让子代理复用主 Agent 的同一套技能。经 env DSH_SKILLS_DIR 传给 dsh 子进程。
SKILLS_ROOT = os.path.join(WORK_DIR, "skills")


def resolve_config_path(explicit: str | None = None) -> str:
    """按 main.py 的口径定位 config.user.json：显式参数 -> 环境变量 -> userData。

    paths.data_path 未 init 时会惰性走兜底目录（Windows 为 %APPDATA%\\sassy-cat），
    与 Electron 主进程 app.getPath('userData') 指向同一处。
    """
    if explicit:
        return explicit
    return os.getenv("SASSY_CAT_CONFIG") or paths.data_path("config.user.json")


def read_dsh_block(cfg) -> dict[str, Any]:
    """读取顶层 dsh 配置块（设置页「dsh 子代理」卡片写入），归纳出四组取值。

    含旧配置只读回退（不自动迁移、不写盘）：
      - 输出上限 / 推理强度：老版本写在 llm.profiles.<active>.extraParams.*
      - 系统提示词：老版本写在 agent.profiles.<active>.dshSystemPrompt / 顶层 agent.dshSystemPrompt
    """
    block = cfg.get("dsh") or {}
    dsh_llm = block.get("llm") or {}
    extra = (cfg.active_llm_profile() or {}).get("extraParams") or {}
    agent_profile = cfg.active_agent_profile() or {}

    # 是否复用主 Agent 激活的 LLM；缺省（None）视为开启
    use_main_llm = block.get("useMainLlm")
    use_main_llm = True if use_main_llm is None else bool(use_main_llm)

    # config_loader.DEFAULTS 会把 dsh.maxTokens 填成内置默认，于是"用户没配"与
    # "用户显式配成默认值"在合并后的配置里不可区分。这里把「缺失或等于内置默认」
    # 一律视为未配置，让升级前写在 llm.*.extraParams.maxTokens 的旧值仍能生效；
    # 用户在设置页保存过一次后，该键会被显式落盘，之后即按显式值优先。
    raw_max_tokens = block.get("maxTokens")
    if raw_max_tokens is None or raw_max_tokens == FALLBACK_MAX_TOKENS:
        legacy = extra.get("maxTokens")
        if legacy is not None:
            raw_max_tokens = legacy  # 旧位置回退

    raw_effort = block.get("reasoningEffort") or extra.get("reasoningEffort") or ""

    configured_prompt = (
        block.get("systemPrompt")
        or agent_profile.get("dshSystemPrompt")  # 旧位置回退
        or cfg.get("agent.dshSystemPrompt")  # 旧·顶层回退
    )

    return {
        "use_main_llm": use_main_llm,
        "llm": dsh_llm,
        "system_prompt": configured_prompt,
        "max_tokens": raw_max_tokens,
        "reasoning_effort": str(raw_effort).strip(),
    }


def load_llm_settings(config_path: str) -> dict[str, Any]:
    """读取 dsh 配置（顶层 dsh 块 + 主 Agent LLM 复用开关），翻译成 DeepSeekHarness 的连接参数。"""
    cfg = config_loader.load_config(config_path)
    profile = cfg.active_llm_profile() or {}
    dsh = read_dsh_block(cfg)

    # 连接参数：默认复用主 Agent 激活 profile；关闭复用时走 dsh 独立连接
    if dsh["use_main_llm"]:
        conn = profile
        llm_source = "main"
    else:
        conn = dsh["llm"]
        llm_source = "dsh"

    base_url = (conn.get("baseUrl") or "").strip() or FALLBACK_BASE_URL
    api_key = (conn.get("apiKey") or "").strip() or FALLBACK_API_KEY
    model = (conn.get("model") or "").strip() or FALLBACK_MODEL

    # initialize 只接受 positive safe integer：写成 "131072" 或非正整数会被 schema 拒掉，
    # 因此这里做解析 + 回退，绝不把非法值透传给 dsh
    max_tokens = FALLBACK_MAX_TOKENS
    if dsh["max_tokens"] is not None:
        try:
            parsed = int(dsh["max_tokens"])
            if parsed > 0:
                max_tokens = parsed
            else:
                logger.warning(
                    "dsh.maxTokens=%r 非正整数，回退 %d", dsh["max_tokens"], FALLBACK_MAX_TOKENS
                )
        except (TypeError, ValueError):
            logger.warning(
                "dsh.maxTokens=%r 无法解析为整数，回退 %d",
                dsh["max_tokens"],
                FALLBACK_MAX_TOKENS,
            )

    # 白名单外的 reasoningEffort 一律不传（非法枚举会让 dsh initialize 失败）
    effort = dsh["reasoning_effort"]
    if effort and effort not in DSH_REASONING_EFFORTS:
        logger.warning(
            "dsh.reasoningEffort=%r 不在 %s 内，已忽略", effort, DSH_REASONING_EFFORTS
        )
        effort = ""
    reasoning_effort = effort or None

    # 系统提示词：配置优先，留空用内置默认
    configured_prompt = dsh["system_prompt"]
    system_prompt = (
        str(configured_prompt).strip() if configured_prompt else DEFAULT_SYSTEM_PROMPT.strip()
    )
    # {shell_guidance} 按当前平台展开；配置里自定义的 prompt 也可以用它
    system_prompt = system_prompt.replace("{shell_guidance}", shell_guidance())

    logger.info(
        "dsh LLM: route=%s model=%s baseUrl=%s maxTokens=%s reasoningEffort=%s "
        "llmSource=%s systemPrompt=%d字",
        DSH_ROUTE,
        model,
        base_url,
        max_tokens,
        reasoning_effort,
        llm_source,
        len(system_prompt),
    )
    return {
        "base_url": base_url,
        "api_key": api_key,
        "model": model,
        "max_tokens": max_tokens,
        "reasoning_effort": reasoning_effort,
        "system_prompt": system_prompt,
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
        # client 侧是 os.environ.copy() 再 update，所以这里只需增量注入。
        # DSH_SYSTEM_PROMPT 被 sdk-minimal 的 system-prompt 行读作 personaPrefix
        # （`process.env.DSH_SYSTEM_PROMPT ?? '<英文默认>'`），链路见模块 docstring。
        # DSH_SKILLS_DIR 被 editor.patch.yml 的 skill-filesystem 行读作 customSkillDirs
        # （逗号分隔），指向主 Agent 的技能库，使 dsh 与主 Agent 共享同一套 skills。
        env={
            "DSH_HOME": DSH_HOME,
            "DSH_SYSTEM_PROMPT": settings["system_prompt"],
            "DSH_SKILLS_DIR": SKILLS_ROOT,
        },
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
