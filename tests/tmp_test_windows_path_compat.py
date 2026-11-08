# -*- coding: utf-8 -*-
"""deepagents 文件路径兼容层验证脚本（手动运行，无 pytest 依赖）。

覆盖本次故障的完整链路（截图里 read_file 报 "Windows absolute paths are not supported"）：

  1. middleware 里的 validate_path 是否已被兼容层接管
  2. 盘符 / UNC / 正斜杠绝对路径放行，且能落到真实文件
  3. 相对路径、以 / 开头的路径都按「工作区根目录」解析（旧实现会落到盘符根）
  4. 危险路径（.. / ~）仍被拒绝（垫片不能顺手把安全边界放宽）
  5. deepagents 内部写入路径（/large_tool_results）落在工作区内
  6. 技能清单里的真实绝对路径可直接 read / ls / glob（原始报错场景）

运行：
    .venv\\Scripts\\python tests\\tmp_test_windows_path_compat.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "python"))

import config_loader  # noqa: E402  确保 paths 初始化与主程序一致
import deepagents  # noqa: E402
from deepagents.middleware import filesystem as fs_middleware  # noqa: E402

from agent.constant import SKILLS_DIR, WORK_DIR  # noqa: E402
from agent.deepagents_path_compat import install, _win_validate_path  # noqa: E402
from agent.shell_backend import create_shell_backend  # noqa: E402

IS_WINDOWS = os.name == "nt"
FAILED = []
SKILL_MD = os.path.join(SKILLS_DIR, "weather-skill", "SKILL.md")


def check(name, cond, detail=""):
    mark = "PASS" if cond else "FAIL"
    if not cond:
        FAILED.append(name)
    print(f"[{mark}] {name}" + (f"  | {detail}" if detail else ""))


def same_path(a, b):
    return os.path.normcase(os.path.abspath(str(a))) == os.path.normcase(os.path.abspath(str(b)))


print(
    f"platform={'windows' if IS_WINDOWS else 'posix'}  "
    f"deepagents={getattr(deepagents, '__version__', '?')}"
)
print(f"workdir={WORK_DIR}")

# 构造 backend 即安装兼容层（见 agent/shell_backend.py）；再显式调一次验证幂等
backend = create_shell_backend(WORK_DIR)
install()

validate = fs_middleware.validate_path

if not IS_WINDOWS:
    check("非 Windows 不做任何改动（validate_path 保持原实现）", validate is not _win_validate_path, repr(validate))
    print("\n非 Windows 平台，跳过 Windows 专项断言。")
    sys.exit(1 if FAILED else 0)

check("兼容层已接管 middleware.validate_path", validate is _win_validate_path, repr(validate))
check("技能文件存在（前置条件）", os.path.isfile(SKILL_MD), SKILL_MD)

# ---------- 1. 盘符绝对路径：放行 + 真实可达 ----------
p = validate(SKILL_MD)
check("盘符绝对路径放行", same_path(p, SKILL_MD), p)
check("解析到真实 SKILL.md", same_path(backend._resolve_path(p), SKILL_MD), str(backend._resolve_path(p)))

r = backend.read(p, limit=5)
content = (r.file_data or {}).get("content") or ""
check("backend.read 可读技能文件", not r.error and "---" in content, str(r.error or content[:40]))

p2 = validate(SKILL_MD.replace("\\", "/"))
check("正斜杠盘符路径放行", same_path(p2, SKILL_MD), p2)

# ---------- 2. 相对路径 / 开头路径 → 工作区根目录 ----------
for name, given in (
    ("相对路径按工作区根目录解析", os.path.join("skills", "weather-skill", "SKILL.md")),
    ("/ 开头按工作区根目录解析", "/skills/weather-skill/SKILL.md"),
    ("反斜杠相对路径按工作区根目录解析", r"skills\weather-skill\SKILL.md"),
):
    got = backend._resolve_path(validate(given))
    check(name, same_path(got, SKILL_MD), f"{given} -> {got}")

# ---------- 3. 旧的 /workspaces 写法不再“碰巧命中” ----------
legacy = backend._resolve_path(validate("/workspaces/py/sassy-cat/runtime/skills"))
check(
    "旧的 /workspaces/... 写法不再指向真实技能目录（换盘即失效的隐患已消除）",
    not same_path(legacy, SKILLS_DIR),
    str(legacy),
)

# ---------- 4. 危险路径仍被拒绝 ----------
for bad in ("../etc/passwd", r"..\Windows\win.ini", "~/secret", r"C:\Windows\..\Users", r"C:\a\..\b"):
    try:
        validate(bad)
    except ValueError:
        check(f"拒绝危险路径 {bad}", True)
    else:
        check(f"拒绝危险路径 {bad}", False)

# ---------- 5. deepagents 内部外迁目录落在工作区内 ----------
evict = backend._resolve_path("/large_tool_results/probe.txt")
check(
    "大结果外迁目录落在工作区内（不再写到盘符根）",
    os.path.normcase(str(evict)).startswith(os.path.normcase(os.path.abspath(WORK_DIR))),
    str(evict),
)

# ---------- 6. 原始报错场景：ls / glob 用技能清单里的路径 ----------
ls_result = backend.ls(SKILLS_DIR)
entries = ls_result.entries or []
check(
    "backend.ls(真实绝对路径) 能列出技能目录",
    not ls_result.error and any(str(e.get("path", "")).rstrip("\\/").endswith("weather-skill") for e in entries),
    str(ls_result.error or [e.get("path") for e in entries][:3]),
)

glob_result = backend.glob("SKILL.md", path=SKILLS_DIR)
matches = glob_result.matches or []
check(
    "backend.glob(真实绝对路径) 能匹配到 SKILL.md",
    not glob_result.error and any(same_path(m.get("path", ""), SKILL_MD) for m in matches),
    str(glob_result.error or len(matches)),
)

# ---------- 7. 直接调内置工具（middleware 层，最接近真实对话） ----------
from deepagents.middleware.filesystem import FilesystemMiddleware  # noqa: E402

class _RuntimeStub:
    """工具函数只用到 tool_call_id 这一个运行时字段。"""

    tool_call_id = "probe-call"


fs_tools = {tool.name: tool for tool in FilesystemMiddleware(backend=backend).tools}

msg = fs_tools["read_file"].func(SKILL_MD, _RuntimeStub(), limit=5)
check(
    "read_file 工具直接吃盘符绝对路径（截图里的原始报错场景）",
    getattr(msg, "status", None) == "success",
    str(msg.content)[:120].replace("\n", " / "),
)

msg = fs_tools["read_file"].func("skills/weather-skill/SKILL.md", _RuntimeStub(), limit=3)
check("read_file 工具吃相对路径", getattr(msg, "status", None) == "success", str(msg.content)[:120])

msg = fs_tools["ls"].func(_RuntimeStub(), SKILLS_DIR)
check(
    "ls 工具吃盘符绝对目录",
    getattr(msg, "status", None) == "success" and "weather-skill" in str(msg.content),
    str(msg.content)[:120],
)

msg = fs_tools["glob"].func("SKILL.md", _RuntimeStub(), path=SKILLS_DIR)
check(
    "glob 工具吃盘符绝对目录",
    getattr(msg, "status", None) == "success" and "SKILL.md" in str(msg.content),
    str(msg.content)[:120],
)

msg = fs_tools["read_file"].func(
    "/workspaces/py/sassy-cat/runtime/skills/weather-skill/SKILL.md", _RuntimeStub(), limit=3
)
check(
    "旧的 /workspaces 写法给出清晰的 not found（不再碰巧命中）",
    getattr(msg, "status", None) == "error",
    str(msg.content)[:120],
)

# ---------- 8. 端到端：真实 agent 图里发一次 read_file（假模型驱动，不联网） ----------
from deepagents import create_deep_agent  # noqa: E402
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402

import agent.deepagents_path_compat as compat  # noqa: E402


class _ToolFake(GenericFakeChatModel):
    """只用来驱动图：GenericFakeChatModel.bind_tools 会抛 NotImplementedError。"""

    def bind_tools(self, tools, **kwargs):
        return self


def _run_read_file_once(thread_id):
    model = _ToolFake(
        messages=iter(
            [
                AIMessage(
                    content="",
                    tool_calls=[{"name": "read_file", "args": {"file_path": SKILL_MD, "limit": 5}, "id": "call_1"}],
                ),
                AIMessage(content="done"),
            ]
        )
    )
    agent = create_deep_agent(model=model, backend=backend, skills=[SKILLS_DIR], tools=[])
    out = agent.invoke(
        {"messages": [{"role": "user", "content": "读一下 weather-skill"}]},
        config={"configurable": {"thread_id": thread_id}},
    )
    tool_msgs = [m for m in out["messages"] if type(m).__name__ == "ToolMessage"]
    return tool_msgs[0] if tool_msgs else None


# 先关掉补丁：应当复现截图里的原始报错（证明因果，而不是"碰巧能跑"）
fs_middleware.validate_path = compat._original_validate_path
bad = _run_read_file_once("probe-e2e-before")
check(
    "关掉补丁可复现截图报错（因果验证）",
    bad is not None
    and getattr(bad, "status", None) == "error"
    and "Windows absolute paths are not supported" in str(bad.content),
    str(bad.content if bad is not None else "no ToolMessage")[:110],
)

# 再装上补丁：同一个 tool call 应成功
fs_middleware.validate_path = compat._win_validate_path
good = _run_read_file_once("probe-e2e-after")
check(
    "装上补丁后同一个 tool call 成功（截图场景修复）",
    good is not None
    and getattr(good, "status", None) == "success"
    and "weather-skill" in str(good.content),
    str(good.content if good is not None else "no ToolMessage")[:110].replace("\n", " / "),
)

print()
if FAILED:
    print(f"FAILED {len(FAILED)} 项：{', '.join(FAILED)}")
    sys.exit(1)
print("全部通过。")