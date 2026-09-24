# -*- coding: utf-8 -*-
"""临时探测：.dsh/home/sessions 下的长目录名是否由 cwd 派生（用完可删）。

用临时 cwd + 临时 dsh_home 跑一轮，再看 sessions 下生成的分组目录名，
若它与 cwd 路径对应，即可确认该目录是 dsh 按工作目录划分的会话分组。
"""

import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "python"))

from agent.tools.dsh import dsh_invoker  # noqa: E402
from deepseek_harness import DeepSeekHarness  # noqa: E402

settings = dsh_invoker.load_llm_settings(dsh_invoker.resolve_config_path())

cwd = tempfile.mkdtemp(prefix="dsh-cwd-check-")
home = tempfile.mkdtemp(prefix="dsh-home-check-")
print("cwd  =", cwd)
print("home =", home)

harness = DeepSeekHarness(
    provider=dsh_invoker.DSH_ROUTE,
    model=settings["model"],
    reasoning_effort=settings["reasoning_effort"],
    max_tokens=settings["max_tokens"],
    cwd=cwd,
    dsh_home=home,
    profile=dsh_invoker.DSH_PROFILE,
    patches=(dsh_invoker.PATCH_FILE,),
    env={"DSH_HOME": home},
    base_url=settings["base_url"],
    api_key=settings["api_key"],
    initialize_timeout_seconds=30.0,
    request_timeout_seconds=None,
)

with harness:
    r = harness.run("只回复两个字：好的", session_id="probe-cwd-check")
    print("返回:", r.final_response)

sessions = os.path.join(home, "sessions")
print("\nsessions 下的条目：")
for name in sorted(os.listdir(sessions)):
    inner = os.listdir(os.path.join(sessions, name))
    print(f"  {name!r} -> {inner}")

print("\n【对比】cwd 规范化 =", cwd.replace(":", "").replace("\\", "-").replace("/", "-"))