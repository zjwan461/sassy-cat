# -*- coding: utf-8 -*-
"""临时探测：给 sdk-minimal 追加候选插件后，dsh 到底下发了哪些工具（用完可删）。

比静态看配置强的地方：真正 boot 一次，因此插件解析失败、依赖缺失、id 冲突
都会在启动或首轮暴露；成功则从 request/header 读回模型实际拿到的工具清单。
"""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "python"))

from deepseek_harness import DeepSeekHarness  # noqa: E402

from agent.tools.dsh import dsh_invoker  # noqa: E402

EXTRA_PATCH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "tmp_dsh_plugins_probe.patch.yml"
)

tools_seen: list[str] = []
event_types: set[str] = set()


def sink(notification) -> None:
    if notification.method != "session.event":
        return
    event = (notification.payload or {}).get("event") or {}
    etype = event.get("type")
    if not etype:
        return
    event_types.add(etype)
    if etype != "request/header":
        return
    header = (event.get("data") or {}).get("header") or {}
    for tool in header.get("tools") or []:
        name = tool.get("name")
        if name and name not in tools_seen:
            tools_seen.append(name)


def main() -> None:
    settings = dsh_invoker.load_llm_settings(dsh_invoker.resolve_config_path())
    os.makedirs(dsh_invoker.WORKSPACE, exist_ok=True)
    os.makedirs(dsh_invoker.DSH_HOME, exist_ok=True)

    harness = DeepSeekHarness(
        provider=dsh_invoker.DSH_ROUTE,
        model=settings["model"],
        reasoning_effort=settings["reasoning_effort"],
        max_tokens=settings["max_tokens"],
        cwd=dsh_invoker.WORKSPACE,
        dsh_home=dsh_invoker.DSH_HOME,
        profile=dsh_invoker.DSH_PROFILE,
        patches=(dsh_invoker.PATCH_FILE, EXTRA_PATCH),
        env={"DSH_HOME": dsh_invoker.DSH_HOME},
        base_url=settings["base_url"],
        api_key=settings["api_key"],
        initialize_timeout_seconds=60.0,
        request_timeout_seconds=None,
    )

    try:
        with harness:
            # 逼它用上待办与搜索：先写计划再执行，顺便验证 todo/write 是否真的流出
            result = harness.run(
                "请先用 todo 工具写下 3 步计划（每步执行一次 shell 的 echo，依次打印 1、2、3），"
                "然后逐步执行，最后用一句话说明完成情况。",
                session_id=f"pluginprobe-{os.getpid()}",
                on_notification=sink,
            )
    except Exception as exc:  # 插件装载失败会在这里现形
        print("FAILED:", type(exc).__name__)
        print(str(exc)[:2000])
        raise

    print("finish_reason:", result.finish_reason)
    print("tools:", tools_seen)
    print("events:", sorted(event_types))


main()