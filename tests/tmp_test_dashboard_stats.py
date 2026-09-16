# -*- coding: utf-8 -*-
"""Dashboard 统计聚合一次性验证脚本（只读查询，不影响生产数据）。

运行：python tests/tmp_test_dashboard_stats.py
"""

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

from server.db import init_db, close_db  # noqa: E402
from server.db import stats_repository  # noqa: E402


async def main():
    await init_db()
    try:
        result = await stats_repository.dashboard_stats(trend_days=7)
        print(json.dumps(result, ensure_ascii=False, indent=2))

        # 基本形状断言
        assert set(result) >= {"chat", "token", "kb", "trend"}
        assert set(result["chat"]) == {"today", "total"}
        assert set(result["token"]) == {"today", "total"}
        for scope in ("today", "total"):
            assert set(result["token"][scope]) == {
                "inputTokens",
                "outputTokens",
                "totalTokens",
            }
            assert result["token"][scope]["totalTokens"] == (
                result["token"][scope]["inputTokens"]
                + result["token"][scope]["outputTokens"]
            )
        assert set(result["kb"]) == {"kbCount", "docCount", "chunkCount", "perKb"}
        assert len(result["trend"]) == 7
        for item in result["trend"]:
            assert set(item) == {"date", "chats", "tokens"}
        print("\n[PASS] dashboard_stats 结构与一致性校验通过")
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
