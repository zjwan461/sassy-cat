# -*- coding: utf-8 -*-
"""验证：执行 alembic 迁移后，根 logger 上应用注册的 handler 不被 fileConfig 清除。"""
import logging
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "python"))

# 模拟 main.py：根 logger 已配置 handler
logging.basicConfig(level=logging.INFO)


class FakeProtocolHandler(logging.Handler):
    """模拟 ProtocolLogHandler，收集日志文本"""
    records = []

    def emit(self, record):
        FakeProtocolHandler.records.append(record.getMessage())


_handler = FakeProtocolHandler()
logging.root.addHandler(_handler)

before = list(logging.root.handlers)

import paths
paths.init(None)

from server.db.database import _run_migrations
_run_migrations()

after = list(logging.root.handlers)

ok = _handler in after
print("handlers before:", len(before), "after:", len(after))
print("protocol handler preserved:", ok)
print("captured during migration:", [r for r in FakeProtocolHandler.records if "迁移" in r or "alembic" in r.lower()][:5])
assert ok, "FAIL: 迁移后 ProtocolLogHandler 被移除"
print("PASS")
