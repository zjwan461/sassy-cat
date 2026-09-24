# -*- coding: utf-8 -*-
"""临时探测：dsh 会话"续聊"的边界（用完可删）。

1) 同一进程内、同一 sessionId 连续两次 run —— 验证能否续聊（第二次应记得第一次说的名字）
2) 新建 harness（等价于"下次启动脚本"）复用同一 sessionId —— 复现 SessionAlreadyExistsError
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "python"))

from agent.tools.dsh import dsh_invoker as m  # noqa: E402

SESSION = "probe-session-reuse"

settings = m.load_llm_settings(m.resolve_config_path(None))

print("=== case 1: 同一进程内、同一 sessionId 连续两次 run ===")
harness = m.build_harness(settings)
with harness:
    r1 = harness.run("我叫阿猫，请记住这个名字，只回复两个字：好的", session_id=SESSION)
    print("R1:", r1.final_response)
    r2 = harness.run("我叫什么名字？只回答名字", session_id=SESSION)
    print("R2:", r2.final_response)

print("=== case 2: 新 harness（等价于下次启动脚本）复用同一 sessionId ===")
try:
    h2 = m.build_harness(settings)
    with h2:
        r3 = h2.run("在吗", session_id=SESSION)
        print("R3:", r3.final_response)
except Exception as exc:  # noqa: BLE001 - 探测脚本，要看到真实异常类型
    print("case 2 失败:", type(exc).__name__, exc)