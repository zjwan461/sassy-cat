# -*- coding: utf-8 -*-
"""桌宠每日打招呼（proactive/greeting）冒烟测试。

覆盖：日期占位去重、回滚、未配置 LLM 走兜底、流式 delta 转发。
运行：.venv\\Scripts\\python.exe tests\\tmp_test_greeting.py
"""

import asyncio
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "python"))

import paths

paths.init(tempfile.mkdtemp(prefix="sassy-greet-test-"))

import config_loader  # noqa: E402
from proactive import greeting  # noqa: E402
from server import bus  # noqa: E402

PASS = 0


def check(name, cond):
    global PASS
    assert cond, f"FAIL: {name}"
    PASS += 1
    print(f"ok - {name}")


class FakeLLM:
    """模拟 astream：产出若干文本块 + 一个空块"""

    def __init__(self, pieces):
        self._pieces = pieces

    async def astream(self, prompt):
        class Chunk:
            def __init__(self, c):
                self.content = c

        for p in self._pieces:
            yield Chunk(p)


async def main():
    # 捕获广播帧
    frames = []

    async def capture(frame, exclude=None):
        frames.append(frame)

    bus.hub.publish_all = capture

    # 加速：去掉宽限与聊天占用
    greeting.GRACE_SECONDS = 0
    greeting._wait_until_idle = lambda: asyncio.sleep(0)  # 占位，稍后被覆盖为 coro

    async def idle_true():
        return True

    greeting._wait_until_idle = idle_true

    state_file = greeting._state_path()

    # --- 1. 日期占位去重 ---
    check("首次占位成功", greeting._claim_today() is True)
    check("重复占位失败", greeting._claim_today() is False)
    with open(state_file, "r", encoding="utf-8") as f:
        st = json.load(f)
    check("状态文件记录今日日期", st.get("lastGreetingDate") == greeting._today())

    # --- 2. 回滚后可再次占位 ---
    greeting._release_claim()
    check("回滚后占位成功", greeting._claim_today() is True)
    greeting._release_claim()

    # --- 3. 未配置 LLM（默认空 profile）→ maybe_greet 走兜底 ---
    frames.clear()
    config_loader.load_config(None)  # 默认配置：baseUrl/model 均空
    check("默认配置视为未配置", greeting._llm_ready() is False)
    greeting._inflight = False
    await greeting.maybe_greet()
    types = [f["type"] for f in frames]
    check("兜底推送 greeting.delta", "greeting.delta" in types)
    check("兜底推送 greeting.completed", "greeting.completed" in types)
    text = frames[-1]["payload"]["text"]
    check("兜底文案非空且来自文案池", text in sum(greeting.FALLBACK_POOL.values(), []))
    # 同日不再触发
    frames.clear()
    greeting._inflight = False
    await greeting.maybe_greet()
    check("同日二次触发被去重", len(frames) == 0)

    # --- 4. 已配置 LLM → 流式逐块 delta + completed ---
    greeting._release_claim()  # 清掉今日标记，允许再次打招呼
    orig_build = greeting.build_chat_llm
    greeting.build_chat_llm = lambda profile: FakeLLM(["喵，", "主人", "欢迎回来😾"])
    # 注入一个非空 profile 使 _llm_ready 为 True
    cfg = config_loader.current()
    cfg._data["llm"]["profiles"]["default"]["baseUrl"] = "http://fake/v1"
    cfg._data["llm"]["profiles"]["default"]["model"] = "fake-model"
    check("注入 profile 后视为已配置", greeting._llm_ready() is True)

    frames.clear()
    greeting._inflight = False
    await greeting.maybe_greet()
    deltas = [f["payload"]["text"] for f in frames if f["type"] == "greeting.delta"]
    check("流式 delta 共 3 块", len(deltas) == 3)
    completed = [f for f in frames if f["type"] == "greeting.completed"]
    check("completed 文本为拼接结果", completed[-1]["payload"]["text"] == "喵，主人欢迎回来😾")

    # --- 5. LLM 抛异常且无输出 → 回退兜底 ---
    greeting._release_claim()

    class BoomLLM:
        async def astream(self, prompt):
            raise RuntimeError("connection refused")
            yield  # pragma: no cover

    greeting.build_chat_llm = lambda profile: BoomLLM()
    frames.clear()
    greeting._inflight = False
    await greeting.maybe_greet()
    completed = [f for f in frames if f["type"] == "greeting.completed"]
    check("异常时回退兜底文案", len(completed) == 1 and
          completed[0]["payload"]["text"] in sum(greeting.FALLBACK_POOL.values(), []))

    greeting.build_chat_llm = orig_build

    # --- 6. 待办清单渲染（提醒分类进提示词） ---
    import datetime as _dt

    def _ms(days=0, hours=0):
        base = _dt.datetime.now() + _dt.timedelta(days=days, hours=hours)
        return int(base.timestamp() * 1000)

    fake_records = [
        {"content": "取快递（逾期）", "next_at": _ms(days=-1), "repeat": "none"},
        {"content": "写周报", "next_at": _ms(hours=2), "repeat": "none"},
        {"content": "团队例会", "next_at": _ms(days=1, hours=-3), "repeat": "weekly"},
        {"content": "拔牙复诊", "next_at": _ms(days=3), "repeat": "none"},
        {"content": "下月缴费", "next_at": _ms(days=20), "repeat": "monthly" if False else "none"},
    ]
    orig_list = greeting.list_reminders
    greeting.list_reminders = lambda status=None, limit=500: fake_records
    section = greeting._reminders_section()
    check("清单含[已逾期]分组", "[已逾期]" in section)
    check("清单含[今天]分组", "[今天]" in section)
    check("清单含[明天]分组", "[明天]" in section)
    check("清单含[近期]分组", "[近期]" in section)
    check("更远期只报条数", "另有 1 条" in section)
    check("重复规则渲染每周", "每周" in section)
    check("提醒内容进入清单", "写周报" in section and "取快递（逾期）" in section)

    # 无提醒时返回空串
    greeting.list_reminders = lambda status=None, limit=500: []
    check("无待办时清单为空", greeting._reminders_section() == "")
    # 读取异常时降级为空串（不阻断打招呼）
    def boom(status=None, limit=500):
        raise RuntimeError("store down")
    greeting.list_reminders = boom
    check("读取异常降级为空", greeting._reminders_section() == "")
    greeting.list_reminders = orig_list

    # 提示词包含待办附录
    greeting.list_reminders = lambda status=None, limit=500: fake_records
    prompt = await greeting._build_prompt()
    check("提示词携带未完成事项段", "[主人未完成事项清单]" in prompt and "写周报" in prompt)
    check("提示词含待办提醒指令", "待办" in prompt)
    greeting.list_reminders = orig_list

    print(f"\nALL PASSED ({PASS} checks)")


asyncio.run(main())
