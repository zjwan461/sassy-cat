# -*- coding: utf-8 -*-
"""present 工具回归：工作区内文件可展示，越界/不存在文件被跳过。

运行：.venv\\Scripts\\python.exe tests\\tmp_test_present.py
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "python")))

import config_loader
from config_loader import AppConfig
from agent.tools.present_tool import present

FAILED = []


def check(name, cond, detail=""):
    print(("[PASS] " if cond else "[FAIL] ") + name + (f"  | {detail}" if detail else ""))
    if not cond:
        FAILED.append(name)


def main():
    original = config_loader._current
    try:
        with tempfile.TemporaryDirectory() as ws, tempfile.TemporaryDirectory() as outside:
            config_loader._current = AppConfig({"agent": {"workspace": ws}})

            target = os.path.join(ws, "demo.txt")
            with open(target, "w", encoding="utf-8") as f:
                f.write("line1\nline2\nline3\n")

            raw = present.invoke({"files": ["demo.txt"], "title": "测试展示"})
            data = json.loads(raw)
            check("返回 type=present", data.get("type") == "present", raw[:120])
            check("标题生效", data.get("title") == "测试展示")
            check("文件被收录", len(data.get("files", [])) == 1)
            item = (data.get("files") or [{}])[0]
            check("相对路径正确", item.get("path") == "demo.txt", str(item.get("path")))
            check("行数统计正确", item.get("lines") == 3, str(item.get("lines")))

            outside_file = os.path.join(outside, "outside.txt")
            with open(outside_file, "w", encoding="utf-8") as f:
                f.write("outside")

            raw = present.invoke({"files": [outside_file]})
            check("拒绝工作区外文件", raw.startswith("没有可展示的文件"), raw[:80])

            raw = present.invoke({"files": ["missing.txt"]})
            check("拒绝不存在的文件", raw.startswith("没有可展示的文件"), raw[:80])
    finally:
        config_loader._current = original

    print("FAILED:", FAILED)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
