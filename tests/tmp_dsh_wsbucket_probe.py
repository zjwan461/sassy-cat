# -*- coding: utf-8 -*-
"""临时探测：sessions 下那层分组目录是按 cwd 还是 runtime_cwd 分桶（用完可删）。

给 cwd 与 runtime_cwd 两个不同的临时目录，看生成的分组目录名对应哪一个。
"""

import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "python"))

from agent.tools.dsh import dsh_invoker  # noqa: E402
from deepseek_harness import DeepSeekHarness  # noqa: E402

settings = dsh_invoker.load_llm_settings(dsh_invoker.resolve_config_path())

cwd = tempfile.mkdtemp(prefix="dsh-A-sessioncwd-")
runtime_cwd = tempfile.mkdtemp(prefix="dsh-B-processcwd-")
home = tempfile.mkdtemp(prefix="dsh-home-")

print("cwd          =", cwd)
print("runtime_cwd  =", runtime_cwd)

harness = DeepSeekHarness(
    provider=dsh_invoker.DSH_ROUTE,
    model=settings["model"],
    reasoning_effort=settings["reasoning_effort"],
    max_tokens=settings["max_tokens"],
    cwd=cwd,
    runtime_cwd=runtime_cwd,
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
    harness.run("只回复两个字：好的", session_id="probe-bucket")

sessions = os.path.join(home, "sessions")
names = sorted(os.listdir(sessions))
print("\nsessions 下的分组目录：")
for n in names:
    print(f"  {n}  ->  {os.listdir(os.path.join(sessions, n))}")


def norm(p: str) -> str:
    return "--" + p.replace(":", "").replace("\\", "-").replace("/", "-") + "--"


print("\ncwd 对应名         :", norm(os.path.abspath(cwd)))
print("runtime_cwd 对应名 :", norm(os.path.abspath(runtime_cwd)))
print("实际分组目录       :", names)