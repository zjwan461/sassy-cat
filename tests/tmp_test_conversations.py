# -*- coding: utf-8 -*-
"""conversations 模块自测（临时数据目录 + SQLite，不污染真实 userData）

用法: python tests/tmp_test_conversations.py
"""
import asyncio
import json
import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

tmp = tempfile.mkdtemp(prefix="sassy-test-")
import paths
paths.init(tmp)

from server.db import init_db, close_db, get_session
from server.db.models import SystemMeta
from server import conversations as c
from sqlalchemy import select

ACTIVE_KEY = c.ACTIVE_KEY


async def _active_meta():
    """直查 system_meta 中激活会话值（绕过 _ensure_active 的自愈逻辑）"""
    async with get_session() as session:
        row = (
            await session.execute(select(SystemMeta).where(SystemMeta.key == ACTIVE_KEY))
        ).scalar_one_or_none()
        return row.value if row else None


async def main():
    await init_db()

    # 1. 首次使用：自动创建默认会话并激活
    aid = await c.active_id()
    assert aid and aid.startswith("conv-"), f"active_id 异常: {aid}"
    lst = await c.list_sorted()
    assert len(lst) == 1 and lst[0]["title"] == "新对话", lst

    # 2. 新建 + 激活（"新对话"按钮路径：默认标题）
    conv2 = await c.create()
    assert await c.active_id() == conv2["id"]
    assert len(await c.list_sorted()) == 2

    # 3. auto_title：默认标题才改名；已改名不覆盖
    assert await c.auto_title(conv2["id"], "帮我写个爬虫") is not None
    assert (await c.get(conv2["id"]))["title"] == "帮我写个爬虫"
    assert await c.auto_title(conv2["id"], "不该覆盖") is None
    assert (await c.get(conv2["id"]))["title"] == "帮我写个爬虫"
    # 自定义标题的会话不被 auto_title 覆盖
    conv_custom = await c.create("已命名")
    assert await c.auto_title(conv_custom["id"], "也不覆盖") is None
    assert (await c.get(conv_custom["id"]))["title"] == "已命名"
    await c.delete(conv_custom["id"])
    long_text = "一二三四五六七八九十一二三四五六七八九十一二三四五六七八九十"
    conv3 = await c.create()
    await c.auto_title(conv3["id"], long_text)
    assert len((await c.get(conv3["id"]))["title"]) == 24, (await c.get(conv3["id"]))["title"]

    # 4. 切换激活
    await c.set_active(aid)
    assert await c.active_id() == aid
    assert await c.set_active("conv-nonexist") is None

    # 5. rename / touch
    await c.rename(aid, "我的主对话")
    assert (await c.get(aid))["title"] == "我的主对话"
    before = (await c.get(conv3["id"]))["updatedAt"]
    time.sleep(1.01)
    await c.touch(conv3["id"])
    assert (await c.get(conv3["id"]))["updatedAt"] > before
    assert (await c.list_sorted())[0]["id"] == conv3["id"]  # 最近更新的排最前

    # 6. 删除非激活会话
    assert await c.delete(conv3["id"]) is True
    assert await c.get(conv3["id"]) is None
    assert await c.active_id() == aid  # 激活不受影响

    # 7. 删除激活会话：自动回退到最近更新的其他会话
    await c.create("占位")  # 再建一个非激活
    await c.set_active(aid)
    assert await c.delete(aid) is True
    assert await c.active_id() != aid and await c.active_id() is not None

    # 8. 删除最后一个：自动补建默认
    for item in list(await c.list_sorted()):
        await c.delete(item["id"])
    lst = await c.list_sorted()
    assert len(lst) == 1 and await c.active_id() == lst[0]["id"]

    # 9. 持久化（模拟重启）：数据在 DB，重新读取一致
    c2 = await c.create("重启前会话")
    assert await c.get(c2["id"]) is not None
    assert await c.active_id() == c2["id"]

    # 10. activeId 悬空（指向被外部删除的会话）：回退到最近更新
    async with get_session() as session:
        row = (
            await session.execute(select(SystemMeta).where(SystemMeta.key == ACTIVE_KEY))
        ).scalar_one()
        row.value = "conv-ghost"
        await session.commit()
    assert await _active_meta() == "conv-ghost"
    assert await c.active_id() in [x["id"] for x in await c.list_sorted()], await c.active_id()
    assert await _active_meta() == await c.active_id()  # 悬空值已被修复持久化

    # 11. 旧 conversations.json 导入 seed：表为空时导入并归档
    await close_db()
    legacy = {
        "version": 1,
        "activeId": "conv-legacy-2",
        "conversations": [
            {"id": "conv-legacy-1", "title": "旧会话一", "createdAt": 100, "updatedAt": 200},
            {"id": "conv-legacy-2", "title": "旧会话二", "createdAt": 150, "updatedAt": 300},
        ],
    }
    with open(paths.data_path("conversations.json"), "w", encoding="utf-8") as f:
        json.dump(legacy, f, ensure_ascii=False)
    # 清空表模拟迁移后首次启动
    import sqlite3
    conn = sqlite3.connect(paths.data_path("messages.sqlite"))
    conn.execute("DELETE FROM conversations")
    conn.execute("DELETE FROM system_meta WHERE key=?", (ACTIVE_KEY,))
    conn.commit()
    conn.close()
    await init_db()
    assert await _active_meta() == "conv-legacy-2", await _active_meta()
    ids = {x["id"] for x in await c.list_sorted()}
    assert ids == {"conv-legacy-1", "conv-legacy-2"}, ids
    assert not os.path.isfile(paths.data_path("conversations.json"))
    assert os.path.isfile(paths.data_path("conversations.json.imported.bak"))

    await close_db()
    print("ALL PASS (11/11)")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
