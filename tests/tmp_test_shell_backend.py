# -*- coding: utf-8 -*-
"""shell 后端验证脚本（手动运行，无 pytest 依赖）。

Windows 验证 PowerShell 管线，macOS/Linux 验证 sh 管线。

运行：
    .venv\\Scripts\\python tests\\tmp_test_shell_backend.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "python"))

import config_loader  # noqa: E402  确保 paths 初始化与主程序一致
from agent.shell_backend import create_shell_backend, resolve_powershell  # noqa: E402
from agent.constant import WORK_DIR  # noqa: E402

IS_WINDOWS = os.name == "nt"
b = create_shell_backend(WORK_DIR)
FAILED = []


def check(name, cond, detail=""):
    mark = "PASS" if cond else "FAIL"
    if not cond:
        FAILED.append(name)
    print(f"[{mark}] {name}" + (f"  | {detail}" if detail else ""))


print(f"platform={'windows' if IS_WINDOWS else 'posix'}  workdir={WORK_DIR}")
if IS_WINDOWS:
    print(f"powershell={resolve_powershell()}")

# ---------- 基础执行 ----------
r = b.execute("Get-Location | Select-Object -ExpandProperty Path" if IS_WINDOWS else "pwd")
check("cwd 为工作区根目录", os.path.realpath(WORK_DIR).lower() in r.output.lower().replace("/", "\\"), r.output.strip()[:120])
check("退出码 0", r.exit_code == 0)

r = b.execute("Write-Output '中文输出测试'" if IS_WINDOWS else "printf '中文输出测试\\n'")
check("中文输出不乱码", "中文输出测试" in r.output and "\ufffd" not in r.output, r.output.strip()[:80])

r = b.execute("cmd /c exit 3" if IS_WINDOWS else "exit 3")
check("非零退出码带标记", r.exit_code == 3 and "[exit code: 3]" in r.output, f"exit={r.exit_code} out={r.output.strip()[:60]}")

# ---------- 错误输出 ----------
r = b.execute("Write-Error 'boom'" if IS_WINDOWS else "echo boom >&2; exit 1")
check("stderr 内容可见", "boom" in r.output, r.output.strip()[:100])
check("启动前缀/临时名不回显", "$ProgressPreference" not in r.output and "sassy-ps-" not in r.output, r.output.strip()[:100])

# ---------- 超时：整棵进程树被清理 ----------
r = b.execute("Start-Sleep -Seconds 10" if IS_WINDOWS else "sleep 10", timeout=1)
check("超时返回 124", r.exit_code == 124, f"exit={r.exit_code}")
check("超时标记", "[timed out after 1s]" in r.output, r.output.strip()[:80])

# ---------- 项目解释器：venv 在 PATH 最前 ----------
r = b.execute(
    'python -c "import sys; print(sys.executable)"'
)
check("python 指向项目 .venv", ".venv" in r.output.lower().replace("\\", "/"), r.output.strip()[:140])

# ---------- 管道 / 重定向 / 相对路径 ----------
r = b.execute("Write-Output 'hello-pipe' | Select-String 'pipe'" if IS_WINDOWS else "echo hello-pipe | grep pipe")
check("管道可用", r.exit_code == 0 and "hello-pipe" in r.output, r.output.strip()[:80])

r = b.execute(
    "Set-Content -Path '_shell_probe.txt' -Value 'ok' -Encoding utf8; Get-Content -Path '_shell_probe.txt'"
    if IS_WINDOWS
    else "echo ok > _shell_probe.txt; cat _shell_probe.txt"
)
check("相对路径写入工作区", r.exit_code == 0 and "ok" in r.output, r.output.strip()[:80])
_probe = os.path.join(WORK_DIR, "_shell_probe.txt")
if os.path.exists(_probe):
    os.remove(_probe)

# ---------- 文件工具与 shell 共用真实路径 ----------
skill_md = os.path.join(WORK_DIR, "skills", "weather-skill", "SKILL.md")
if os.path.exists(skill_md):
    rel = os.path.relpath(skill_md, WORK_DIR).replace("\\", "/")
    got = b.read(rel)
    content = getattr(got, "file_data", None) or {}
    check("文件工具支持工作区相对路径", "weather" in str(content.get("content", "")).lower(), str(content)[:80])
    got_abs = b.read(skill_md.replace("\\", "/"))
    check("文件工具支持真实绝对路径", getattr(got_abs, "error", None) is None, str(getattr(got_abs, "error", "")))

print()
print(f"共 {len(FAILED)} 个失败" if FAILED else "全部通过")
sys.exit(1 if FAILED else 0)
