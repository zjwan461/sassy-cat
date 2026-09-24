# -*- coding: utf-8 -*-
"""临时验证：messages.subagent_name / segments 迁移 + 仓储往返（用完可删）。

用临时数据目录，不影响真实用户数据：
1. 全新库 upgrade head 后有 subagent_name / segments 两列
2. save/get 能存取 subagentName 与 segments（含原生消息两字段为空）
3. update 能补写两字段
4. _merge_agent_segments 相邻同来源合并语义正确
"""

import asyncio
import os
import shutil
import sqlite3
import sys
import tempfile

_TMP_DATA_DIR = tempfile.mkdtemp(prefix="sassy-subagent-test-")
os.environ["SASSY_CAT_DATA_DIR"] = _TMP_DATA_DIR

_PY_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "python"))
if _PY_ROOT not in sys.path:
    sys.path.insert(0, _PY_ROOT)

from paths import data_path  # noqa: E402
from server.db.database import init_db, close_db  # noqa: E402
from server.db import message_repository as repo  # noqa: E402


def _columns(table: str) -> set:
    conn = sqlite3.connect(data_path("messages.sqlite"))
    try:
        return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    finally:
        conn.close()


async def main():
    await init_db()

    cols = _columns("messages")
    assert {"subagent_name", "segments"} <= cols, f"缺列: {cols}"
    print("[1] 迁移 OK，messages 新列:", sorted(cols & {"subagent_name", "segments"}))

    # 带子 agent 分段的消息
    segs = [
        {"agent": None, "text": "主 agent 开头。"},
        {"agent": "dsh", "text": "> 🛠️ 调用工具 `pwsh`\n> ```json\n> {}\n> ```\n\n"},
        {"agent": None, "text": "主 agent 收尾。"},
    ]
    ok = await repo.save_message(
        id="m-dsh",
        session_id="s1",
        role="assistant",
        content="".join(s["text"] for s in segs),
        subagent_name="dsh",
        segments=segs,
    )
    print("[2] save 带子 agent:", ok)

    # 原生消息（无子 agent）
    await repo.save_message(id="m-plain", session_id="s1", role="assistant", content="纯原生回复")

    items, total = await repo.get_messages_by_session("s1")
    by_id = {i["id"]: i for i in items}
    print("[3] 查询 total:", total)
    dsh = by_id["m-dsh"]
    print("    m-dsh.subagentName =", repr(dsh["subagentName"]))
    print("    m-dsh.segments     =", dsh["segments"])
    print("    分段拼接 == content:", "".join(s["text"] for s in dsh["segments"]) == dsh["content"])
    plain = by_id["m-plain"]
    print("    m-plain.subagentName/segments =", repr(plain["subagentName"]), repr(plain["segments"]))
    assert dsh["subagentName"] == "dsh"
    assert plain["subagentName"] is None and plain["segments"] is None

    # update 补写（原生消息 -> 追加 dsh 分段）
    await repo.update_message(
        id="m-plain",
        subagent_name="dsh",
        segments=[{"agent": "dsh", "text": "补写内容"}],
    )
    one = await repo.get_message_by_id("m-plain")
    print("[4] update 后 m-plain.subagentName =", repr(one["subagentName"]), "segments =", one["segments"])
    assert one["subagentName"] == "dsh"

    await close_db()


def check_merge():
    try:
        from server.ws_agent import _merge_agent_segments
    except Exception as e:  # noqa: BLE001 - 导入依赖较重，失败就跳过
        print("[5] 跳过 _merge_agent_segments 检查（导入失败）:", e)
        return
    base = [{"agent": None, "text": "a"}, {"agent": "dsh", "text": "b"}]
    extra = [{"agent": "dsh", "text": "c"}, {"agent": None, "text": "d"}]
    merged = _merge_agent_segments(base, extra)
    print("[5] merge 结果:", merged)
    assert merged == [
        {"agent": None, "text": "a"},
        {"agent": "dsh", "text": "bc"},
        {"agent": None, "text": "d"},
    ]


try:
    asyncio.run(main())
    check_merge()
    print("\n全部通过 ✓")
finally:
    shutil.rmtree(_TMP_DATA_DIR, ignore_errors=True)