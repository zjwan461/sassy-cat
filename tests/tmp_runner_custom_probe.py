# -*- coding: utf-8 -*-
"""临时探测：runner 的 custom 分支从 {"agent", "text"} 取值（用完可删）。

覆盖三点：
1) dict 结构取 text / agent
2) 兼容直接写 str 的旧写法
3) custom 文本计入 done 的 final_text（保证落库正文与显示一致）
"""

import os
import sys
import threading

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "python"))

from agent import runner  # noqa: E402

events = []
runner._safe_put = lambda q, event: events.append(event)  # 绕过 janus 队列


class FakeState:
    next = ()


class FakeAgent:
    """只产出 custom 事件，避免构造 AIMessageChunk。"""

    def stream(self, payload, config=None, stream_mode=None, subgraphs=None):
        yield ("ns", "custom", {"agent": "dsh", "text": "你好"})
        yield ("ns", "custom", {"agent": "dsh", "text": "，世界"})
        yield ("ns", "custom", "裸字符串写法")

    def get_state(self, config):
        return FakeState()


runner._worker_stream(FakeAgent(), None, {}, None, threading.Event())

for event in events:
    print(event)

done = [e for e in events if e["kind"] == "done"][0]
print("done 全文:", repr(done["text"]))