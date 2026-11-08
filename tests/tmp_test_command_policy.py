# -*- coding: utf-8 -*-
"""execute 免确认白名单验证脚本（手动运行，无 pytest 依赖）。

覆盖 agent/command_policy.py 的安全边界：
  1. 放行：跑 skills/<技能>/scripts/*.py（相对 / 盘符绝对 / 反斜杠 / 带前置 Set-Location）
  2. 拦截：非技能脚本、shell 拼接与重定向、越界目录、通配、缺失文件、空命令
  3. apply_execute_allowlist：True / False / 缺省 / 自带 when 的组合语义
  4. 与 engine 的接线：agent.autoApproveSkillScripts 开关（缺省开 / 关闭 / 用户配置覆盖）

运行：
    .venv\\Scripts\\python tests\\tmp_test_command_policy.py
"""

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "python"))

import config_loader  # noqa: E402  确保 paths 初始化与主程序一致
from agent.command_policy import apply_execute_allowlist, is_auto_approved  # noqa: E402
from agent.constant import WORK_DIR  # noqa: E402

FAILED = []


def check(name, cond, detail=""):
    mark = "PASS" if cond else "FAIL"
    if not cond:
        FAILED.append(name)
    print(f"[{mark}] {name}" + (f"  | {detail}" if detail else ""))


SKILL_DIR_REL = "skills/weather-skill"
SCRIPT_REL = "skills/weather-skill/scripts/fetch_weather.py"
SCRIPT_ABS = os.path.join(WORK_DIR, "skills", "weather-skill", "scripts", "fetch_weather.py")

if not os.path.isfile(SCRIPT_ABS):
    print(f"前置条件失败：找不到 {SCRIPT_ABS}")
    sys.exit(1)

# ---------- 1. 应当放行 ----------
ALLOWED = [
    ("相对脚本路径", f"python {SCRIPT_REL} --lat 22.5445741 --lon 114.0545429 --resolution daily"),
    ("盘符绝对脚本路径", f'python "{SCRIPT_ABS}" --lat 1'),
    ("正斜杠绝对脚本路径", f"python {SCRIPT_ABS.replace(os.sep, '/')} --lat 1"),
    ("反斜杠相对脚本路径", r"python skills\weather-skill\scripts\fetch_weather.py --lat 1"),
    (
        "截图里的写法：Set-Location + 相对脚本",
        f"Set-Location '{os.path.dirname(os.path.dirname(SCRIPT_ABS))}'; python scripts/fetch_weather.py --lat 1",
    ),
    ("相对 cd + 脚本", "cd skills/weather-skill; python scripts/fetch_weather.py"),
    ("多行分隔", f"python {SCRIPT_REL} --lat 1\npython {SCRIPT_REL} --lat 2"),
    (
        "技能子包脚本",
        "python skills/comfyui-image-studio/scripts/zimage/client.py --help",
    ),
]
for name, command in ALLOWED:
    if os.name != "nt" and "Set-Location" in command:
        continue  # 切目录规则是 Windows 语义，POSIX 下不验证
    check(f"放行：{name}", is_auto_approved(command), command[:80])

# ---------- 2. 必须拦截 ----------
DENIED = [
    ("空命令", ""),
    ("非技能目录脚本", "python runtime/hello.py"),
    ("python -c", 'python -c "print(1)"'),
    ("python -m", "python -m http.server"),
    ("拼接删除", f"python {SCRIPT_REL}; Remove-Item runtime/hello.py"),
    ("管道", f"python {SCRIPT_REL} | Out-File out.txt"),
    ("重定向", f"python {SCRIPT_REL} > out.txt"),
    ("反引号注入", f"python {SCRIPT_REL} `whoami`"),
    ("变量展开", f"python {SCRIPT_REL} $env:USERPROFILE"),
    ("调用运算符", "python skills/weather-skill/scripts/fetch_weather.py & calc"),
    ("通配符", "python skills/*/scripts/*.py"),
    ("直接跑系统命令", "Get-Content C:/Windows/win.ini"),
    ("越界 cd", "Set-Location C:/Windows; python scripts/fetch_weather.py"),
    ("cd 到工作区外", "Set-Location ..; python x.py"),
    ("相对路径越界", r"python ..\..\evil.py"),
    ("技能目录下非 scripts 的 py", "python skills/netease-mail/tests/test_net163_mail.py"),
    ("不存在的脚本", "python skills/weather-skill/scripts/not_exists.py"),
    ("只看脚本名", "python fetch_weather.py"),
]
for name, command in DENIED:
    check(f"拦截：{name}", not is_auto_approved(command), command[:80])

# ---------- 3. apply_execute_allowlist 组合语义 ----------
check("execute=False 原样返回", apply_execute_allowlist({"execute": False}) == {"execute": False})
check("未配置 execute 原样返回", apply_execute_allowlist({"write_file": True}) == {"write_file": True})

merged = apply_execute_allowlist({"execute": True})
exec_cfg = merged.get("execute") or {}
check("execute=True 升级为带 when 的配置", callable(exec_cfg.get("when")), repr(exec_cfg))
check("默认带上 allowed_decisions", exec_cfg.get("allowed_decisions") == ["approve", "reject"], repr(exec_cfg))


def _req(command):
    return SimpleNamespace(tool_call={"name": "execute", "args": {"command": command}})


check("谓词：白名单命令不打断", exec_cfg["when"](_req(f"python {SCRIPT_REL} --lat 1")) is False)
check("谓词：普通命令仍打断", exec_cfg["when"](_req("Remove-Item runtime/hello.py")) is True)
check("谓词：结构异常时按需确认", exec_cfg["when"](SimpleNamespace()) is True)

external_never = apply_execute_allowlist(
    {"execute": {"allowed_decisions": ["approve", "reject"], "when": lambda req: False}}
)["execute"]["when"]
check(
    "外部 when 说“不打断”时，本层不会把它变回打断",
    external_never(_req("Remove-Item runtime/hello.py")) is False,
)

external_always = apply_execute_allowlist(
    {"execute": {"allowed_decisions": ["approve", "reject"], "when": lambda req: True}}
)["execute"]["when"]
check(
    "外部 when 说“打断”时，白名单仍可放宽",
    external_always(_req(f"python {SCRIPT_REL} --lat 1")) is False,
)

# ---------- 4. 与 engine / 配置开关的接线 ----------
import json  # noqa: E402
import tempfile  # noqa: E402

from config_loader import AppConfig  # noqa: E402
from agent.engine import _resolve_interrupt_on  # noqa: E402


def _cfg(**agent_cfg):
    return AppConfig({"agent": {"interruptOn": {"execute": True, "write_file": True}, **agent_cfg}})


on = _resolve_interrupt_on(_cfg())
check("缺省（未配开关）：execute 升级为带 when 的配置", callable((on.get("execute") or {}).get("when")))
check(
    "缺省：技能脚本免确认",
    on["execute"]["when"](_req(f"python {SCRIPT_REL} --lat 1")) is False,
)
check("缺省：普通命令仍确认", on["execute"]["when"](_req("Remove-Item runtime/hello.py")) is True)
check("缺省：write_file 仍保持布尔 True", on.get("write_file") is True)

off = _resolve_interrupt_on(_cfg(autoApproveSkillScripts=False))
check("开关关闭：execute 保持 True（每条都确认）", off.get("execute") is True)

# 用户配置文件（Electron 写的就是这个 agent.autoApproveSkillScripts 路径）
user_cfg_path = os.path.join(tempfile.mkdtemp(), "config.user.json")
with open(user_cfg_path, "w", encoding="utf-8") as f:
    json.dump({"agent": {"autoApproveSkillScripts": False}}, f)
cfg_user = config_loader.load_config(user_cfg_path)
check("用户配置关闭后：execute 保持 True", _resolve_interrupt_on(cfg_user).get("execute") is True)

print()
if FAILED:
    print(f"FAILED {len(FAILED)} 项：{', '.join(FAILED)}")
    sys.exit(1)
print("全部通过。")