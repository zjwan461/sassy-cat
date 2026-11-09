# -*- coding: utf-8 -*-
"""工作区选择回归：配置解析、提示词注入、execute 白名单的 cwd 跟随。

运行：.venv\\Scripts\\python.exe tests\\tmp_test_workspace.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "python")))

import config_loader
from config_loader import AppConfig
from agent.workspace import default_workspace, resolve_workspace
from agent.prompts import build_system_prompt
from agent import command_policy

FAILED = []


def check(name, cond, detail=""):
    print(("[PASS] " if cond else "[FAIL] ") + name + (f"  | {detail}" if detail else ""))
    if not cond:
        FAILED.append(name)


def main():
    # 1) 缺省：回退应用内部 runtime
    check("缺省工作区 = 应用 runtime", resolve_workspace(AppConfig({})) == default_workspace())

    # 2) 自定义目录：解析、提示词、白名单 cwd 全部跟随
    with tempfile.TemporaryDirectory() as ws:
        cfg = AppConfig({"agent": {"workspace": ws}})
        resolved = resolve_workspace(cfg)
        check("自定义工作区解析为绝对路径", os.path.normcase(resolved) == os.path.normcase(ws), resolved)

        prompt = build_system_prompt("", workspace=resolved)
        check("提示词包含工作区根目录", ws in prompt)
        check(
            "提示词包含技能库绝对路径",
            os.path.join(default_workspace(), "skills").replace("\\", "/") in prompt
            or os.path.join(default_workspace(), "skills") in prompt,
        )
        check(
            "提示词无残留占位符",
            all(p not in prompt for p in ("{workspace}", "{skills_dir}", "{todo_dir}")),
        )

        # execute 白名单：允许在工作区内 Set-Location，禁止跳到工作区外
        original = config_loader._current
        try:
            config_loader._current = cfg
            check("允许 cd 到当前工作区", command_policy.is_auto_approved(f'Set-Location "{ws}"'))
            check("拒绝 cd 到工作区外", not command_policy.is_auto_approved('Set-Location "C:/Windows"'))
        finally:
            config_loader._current = original

    # 3) 配置的工作区不存在：告警并回退默认
    cfg = AppConfig({"agent": {"workspace": "Z:/definitely/not/a/real/dir"}})
    check("不存在的工作区回退默认", resolve_workspace(cfg) == default_workspace())

    print("FAILED:", FAILED)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
