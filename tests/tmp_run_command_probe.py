"""run_command 修复探针：验证 cmd /c 不再被改写、start 标题与目标校验生效。

注意：本探针不真正启动浏览器（第 6 项只做命令串装配验证）。
运行：.venv\\Scripts\\python.exe tests\\tmp_run_command_probe.py
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "python"))

from agent.tools.builtin_tools import (  # noqa: E402
    work_dir,
    run_command,
    _check_start_targets,
    _convert_virtual_path,
    _decode_candidates,
    _decode_output,
    _fix_start_title,
    _validate_windows_command,
)


def call(cmd, timeout=60):
    """兼容 @tool 包装后的调用方式。"""
    try:
        return run_command.invoke({"command": cmd, "timeout": timeout})
    except AttributeError:
        return run_command(cmd, timeout)


def build(cmd):
    """复刻 run_command 的真实路径转换 + 命令串装配（不执行）。"""
    real = []
    for idx, seg in enumerate(cmd):
        real.extend(_convert_virtual_path(seg, idx))
    problem = _validate_windows_command(real)
    real = _fix_start_title(real)
    if problem is None:
        problem = _check_start_targets(real)
    command_str = subprocess.list2cmdline(real) if os.name == "nt" else " ".join(real)
    return command_str, problem


def main():
    print("=" * 72)
    print("work_dir =", work_dir)
    print("=" * 72)

    print("\n[1] 开关参数不再被当作虚拟路径")
    for seg in ["/c", "/k", "/A", "/TS", "/help", "/?", "-v"]:
        print(f"    {seg!r:10} -> {_convert_virtual_path(seg, 1)}")
    print("    '/skills/README.md' ->", _convert_virtual_path("/skills/README.md", 1))
    print("    './code/x.html'     ->", _convert_virtual_path("./code/x.html", 1))

    print("\n[2] 缺少 /c 的 cmd 调用被拦截（防止假成功）")
    print("   ", repr(call(["cmd", "start", "msedge", "x"]))[:200])
    print("   ", repr(call(["cmd", "/k", "dir"]))[:160])

    print("\n[3] 正常 cmd /c 调用（真实执行）")
    print("   ", repr(call(["cmd", "/c", "echo", "hello"])))
    print("   ", repr(call(["cmd", "/c", "dir", "/skills"]))[:220])

    print("\n[4] start 打开不存在的文件：直接报错，不再假成功")
    print("   ", repr(call(["cmd", "/c", "start", "msedge", "/dsh/workspace/index.html"]))[:400])

    print("\n[5] start 标题自动补空标题的命令串装配（不执行）")
    for cmd in (
        ["cmd", "/c", "start", "msedge", "/.dsh/workspace/index.html"],
        ["cmd", "/c", "start", "/skills/weather-skill/README.md"],
        ["cmd", "/c", "start", "msedge", "https://example.com"],
        ["cmd", "/c", "start", "", "/skills/weather-skill/README.md"],
        ["cmd", "/c", "start", "/B", "notepad"],
    ):
        cmd_str, problem = build(cmd)
        print(f"    {cmd}\n      -> {cmd_str}\n      -> problem={problem!r}")

    print("\n[6] 目标文件真实存在时 start 是否可放行（存在则仅装配，不启动）")
    target = os.path.join(work_dir, "skills", "weather-skill", "README.md")
    print("    exists:", os.path.exists(target))
    print("    _fix_start_title ->",
          _fix_start_title(_convert_virtual_path("/skills/weather-skill/README.md", 1)))

    print("\n[7] 输出解码：GBK 字节不再变成乱码")
    print("    GBK 字节 ->", repr(_decode_output("驱动器 E 中的卷是 SSD2".encode("gbk"))))
    print("    UTF-8 字节 ->", repr(_decode_output("目录索引 中文".encode("utf-8"))))
    print("    候选解码方案 ->", _decode_candidates())

    print("\n[8] start 端到端（/B + /wait，不弹窗、不启动浏览器）")
    print("   ", repr(call(["cmd", "/c", "start", "", "/B", "/wait", "cmd", "/c", "echo", "STARTED_OK"])))
    print("   ", repr(call(["cmd", "/c", "start", "/B", "/wait", "cmd", "/c", "echo", "NO_TITLE"])))

    print("\n[9] 引号参数 / 内置命令 / 多余引号 三个回归点")
    print("    带引号参数 ->", repr(call(["python", "-c", "print(123)"])))
    print("    cmd /c 后接 python ->", repr(call(["cmd", "/c", "python", "-c", "print(456)"])))
    print("    不带 cmd 的 dir ->", repr(call(["dir", "/skills"]))[:120])
    print("    不带 cmd 的 echo ->", repr(call(["echo", "hello"])))
    print("    cmd /c echo ->", repr(call(["cmd", "/c", "echo", "hello"])))


if __name__ == "__main__":
    main()