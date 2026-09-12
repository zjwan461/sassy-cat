# -*- coding: utf-8 -*-
"""提醒事项功能回归自测：数据层 + 工具层 + 推送链路。

运行方式（项目根目录）：
  .venv\\Scripts\\python.exe tests\\tmp_test_reminders.py
使用临时 sqlite，不污染真实数据。
"""
import asyncio
import json
import os
import sys
import tempfile
import time

# 脚本位于 tests/ 下，python 包位于项目根 python/
_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_here, "..", "python"))

from agent import engine, reminders


def log(name, ok, extra=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {extra}")


def main():
    # 用临时 sqlite 隔离，避免污染真实 checkpoints.sqlite
    tmp_db = os.path.join(tempfile.gettempdir(), "reminder_selftest.sqlite")
    if os.path.exists(tmp_db):
        os.remove(tmp_db)
    engine.init_db(tmp_db)

    now = int(time.time() * 1000)
    DAY = 24 * 3600 * 1000

    # 1. 创建一次性提醒
    r1 = reminders.add_reminder("测试：开会", next_at=now + 60000)
    log("add 一次性", r1["id"].startswith("rm-") and r1["status"] == "active")
    rid = r1["id"]

    # 2. 读取
    got = reminders.get_reminder(rid)
    log("get", got is not None and got["content"] == "测试：开会")

    # 3. 列表过滤
    lst = reminders.list_reminders(status="active")
    log("list active 包含", any(x["id"] == rid for x in lst))

    # 4. 到期判断
    due = reminders.due_reminders(now_ms=now + 120000)
    log("due 命中未来+60s", any(x["id"] == rid for x in due))
    due2 = reminders.due_reminders(now_ms=now + 1000)
    log("due 未命中(未到点)", not any(x["id"] == rid for x in due2))

    # 5. 一次性触发推进 -> done
    rec = reminders.advance_after_fire(r1, now_ms=now + 120000)
    log("一次性触发后 done", rec["status"] == "done")
    log(
        "触发后不在 active",
        not any(x["id"] == rid for x in reminders.list_reminders(status="active")),
    )

    # 6. 重复 daily 推进（注意：advance 原地修改 r2，先保存原始 next_at）
    r2 = reminders.add_reminder("测试：每天喝水", next_at=now + 1000, repeat="daily")
    rid2 = r2["id"]
    orig2 = r2["next_at"]
    rec2 = reminders.advance_after_fire(r2, now_ms=now + 5000)
    expected = orig2 + DAY
    log("daily 推进 +24h", rec2["next_at"] == expected and rec2["status"] == "active")

    # 7. interval 每2小时
    r3 = reminders.add_reminder(
        "测试：每2小时", next_at=now + 1000, repeat="interval",
        repeat_every=2, repeat_unit="hour",
    )
    orig3 = r3["next_at"]
    rec3 = reminders.advance_after_fire(r3, now_ms=now + 5000)
    expected3 = orig3 + 2 * 3600 * 1000
    log("interval 推进 +2h", rec3["next_at"] == expected3)

    # 8. daily 超过 repeat_until -> done
    r4 = reminders.add_reminder(
        "测试：截止", next_at=now + 1000, repeat="daily", repeat_until=now + 2000
    )
    rec4 = reminders.advance_after_fire(r4, now_ms=now + 5000)
    log("超过 repeat_until -> done", rec4["status"] == "done")

    # 9. cancel / complete
    r5 = reminders.add_reminder("测试：取消", next_at=now + 999999)
    log("cancel 成功", reminders.cancel_reminder(r5["id"]))
    log(
        "cancel 后不再 active",
        not any(x["id"] == r5["id"] for x in reminders.list_reminders(status="active")),
    )

    r6 = reminders.add_reminder("测试：完成", next_at=now + 999999)
    log("complete 成功", reminders.mark_done(r6["id"]))
    log(
        "complete 后 done 列表包含",
        any(x["id"] == r6["id"] for x in reminders.list_reminders(status="done")),
    )

    # 10. 时间解析
    log("parse 完整格式", reminders.parse_time_text("2026-08-21 15:30:00") is not None)
    log("parse 分钟格式", reminders.parse_time_text("2026-08-21 15:30") is not None)
    log("parse 非法", reminders.parse_time_text("not-a-time") is None)

    # ============ 工具层（@tool 返回 StructuredTool，用 .invoke） ============
    import agent.reminder_tools as rt

    res = rt.create_reminder.invoke({"content": "测工具-相对", "in_minutes": 5})
    log("工具-相对时间", "提醒已设置" in res, res)
    rec_t = next(
        x for x in reminders.list_reminders(status="active")
        if x["content"] == "测工具-相对"
    )
    log("工具-内容落库", rec_t["next_at"] > now and rec_t["status"] == "active")

    res = rt.create_reminder.invoke({"content": "bad", "at": "not-a-time"})
    log("工具-非法时间拒绝", "无法解析" in res, res)

    res = rt.create_reminder.invoke({"content": "过期", "at": "2000-01-01 00:00"})
    log("工具-过期时间拒绝", "已过期" in res, res)

    res = rt.create_reminder.invoke(
        {"content": "测工具-每天", "at": "2099-01-01 08:00", "repeat": "daily"}
    )
    log("工具-重复daily", "每天" in res and "提醒已设置" in res, res)

    res = rt.create_reminder.invoke(
        {"content": "测工具-间隔", "in_minutes": 60, "repeat": "interval",
         "repeat_every": 2, "repeat_unit": "hour"}
    )
    log("工具-interval", "每2小时" in res, res)

    res = rt.create_reminder.invoke({"content": "空内容", "in_minutes": 5, "repeat": "badrule"})
    log("工具-非法repeat", "仅支持" in res, res)

    lst = rt.list_reminders.invoke({"status": "active"})
    log("工具-list", "测工具-相对" in lst and "[rm-" in lst, lst[:80])

    res = rt.complete_reminder.invoke({"reminder_id": rec_t["id"]})
    log("工具-complete", "已标记为完成" in res, res)

    res2 = rt.cancel_reminder.invoke({"reminder_id": rec_t["id"]})
    log("工具-complete后不可再操作", "未找到提醒" in res2 and "已取消" not in res2, res2)

    # ============ 推送链路（reminder_runner，mock hub） ============
    import server.bus as server_bus
    from proactive import reminder_runner

    class FakeHub:
        def __init__(self):
            self.frames = []

        async def publish_all(self, frame, exclude=None):
            self.frames.append(frame)

    fake = FakeHub()
    server_bus.hub = fake

    pushed = reminders.add_reminder("推送测试-到点", next_at=now - 1000)
    asyncio.run(reminder_runner._due_and_fire_once())

    types = [f["type"] for f in fake.frames]
    log("推送-proactive.reminder", "proactive.reminder" in types, str(types))
    log("推送-pet.command", "pet.command" in types, str(types))
    pc = next((f for f in fake.frames if f["type"] == "pet.command"), None)
    log(
        "推送-action=remind+text",
        pc is not None and pc["payload"].get("action") == "remind"
        and "推送测试-到点" in pc["payload"].get("text", ""), str(pc),
    )
    pr = next((f for f in fake.frames if f["type"] == "proactive.reminder"), None)
    log(
        "推送-reminderId",
        pr is not None and pr["payload"].get("reminderId") == pushed["id"],
    )
    log("推送-一次性触发后done", reminders.get_reminder(pushed["id"])["status"] == "done")

    # 重复提醒触发后推进到 future
    rec_day = reminders.add_reminder("推送测试-每日", next_at=now, repeat="daily")
    fake2 = FakeHub()
    server_bus.hub = fake2
    asyncio.run(reminder_runner._due_and_fire_once())
    g2 = reminders.get_reminder(rec_day["id"])
    log(
        "推送-重复触发后推进",
        g2["status"] == "active" and g2["next_at"] > now + 3600 * 1000,
    )
    pr_dur = next((f for f in fake2.frames if f["type"] == "proactive.reminder"), None)
    log("推送-携带durationMs", pr_dur is not None and pr_dur["payload"].get("durationMs") == 8000)

    # ============ 配置读取与钳制（reminder_runner） ============
    import config_loader as cl
    from proactive import reminder_runner as rr

    cl.load_config(None)
    log("配置-默认轮询5s", rr._poll_interval() == 5)
    log("配置-默认气泡8000ms", rr._bubble_duration_ms() == 8000)

    cfg_path = os.path.join(tempfile.gettempdir(), "reminder_cfg_selftest.json")
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump({"pet": {"reminders": {"pollIntervalSeconds": 99, "bubbleDurationMs": 50000}}}, f)
    cl.load_config(cfg_path)
    log("配置-轮询上限钳制30", rr._poll_interval() == 30)
    log("配置-气泡上限钳制30000", rr._bubble_duration_ms() == 30000)

    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump({"pet": {"reminders": {"pollIntervalSeconds": 1, "bubbleDurationMs": 500}}}, f)
    cl.load_config(cfg_path)
    log("配置-轮询下限钳制3", rr._poll_interval() == 3)
    log("配置-气泡下限钳制3000", rr._bubble_duration_ms() == 3000)

    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump({"pet": {"reminders": {"pollIntervalSeconds": "abc", "bubbleDurationMs": "xyz"}}}, f)
    cl.load_config(cfg_path)
    log("配置-非法值回退默认", rr._poll_interval() == 5 and rr._bubble_duration_ms() == 8000)
    os.remove(cfg_path)
    cl.load_config(None)

    # ============ 清理测试数据 ============
    n = 0
    for r in reminders.list_reminders(status=None):
        reminders.cancel_reminder(r["id"])
        n += 1
    print(f"清理 {n} 条测试数据")
    print("自测完成")


if __name__ == "__main__":
    main()