# -*- coding: utf-8 -*-
"""临时探测：从 dsh 落盘的会话 JSONL 统计事件类型与 data 字段（用完可删）。

用来回答"哪些事件/字段真有值、值得在 UI 渲染"，比翻运行时二进制可靠：
遍历 $DSH_HOME 下的会话日志，按事件类型聚合出现次数与 data 键集合，
并抽样打印 usage / interrupted / error / meta / reason 这些关键字段的真实取值。
"""

from __future__ import annotations

import collections
import glob
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "python"))

from agent.tools.dsh import dsh_invoker  # noqa: E402

# 想确认"到底有没有值"的字段
DETAIL_KEYS = ("usage", "interrupted", "error", "meta", "reason", "todos", "stream")


def session_files() -> list[str]:
    pattern = os.path.join(dsh_invoker.DSH_HOME, "**", "*.jsonl")
    return sorted(glob.glob(pattern, recursive=True))


def main() -> None:
    files = session_files()
    print(f"DSH_HOME = {dsh_invoker.DSH_HOME}")
    print(f"找到会话文件 {len(files)} 个：")
    for path in files[-8:]:
        rel = os.path.relpath(path, dsh_invoker.DSH_HOME)
        print(f"    {rel}  ({os.path.getsize(path)} bytes)")

    counts: collections.Counter = collections.Counter()
    keys: dict[str, set] = collections.defaultdict(set)
    samples: dict[str, dict] = {}

    for path in files:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(obj, dict) or "type" not in obj:
                    continue
                etype = obj["type"]
                counts[etype] += 1
                data = obj.get("data")
                if not isinstance(data, dict):
                    continue
                keys[etype].update(data.keys())
                for special in DETAIL_KEYS:
                    slot = samples.setdefault(etype, {})
                    if special in data and special not in slot:
                        slot[special] = data[special]

    print(f"\n事件类型 {len(counts)} 种，共 {sum(counts.values())} 条：")
    for etype, n in counts.most_common():
        print(f"  {n:5d}  {etype:26s} data keys = {sorted(keys[etype])}")

    print("\n关键字段样例：")
    for etype, sample in sorted(samples.items()):
        for key, value in sample.items():
            if key == "stream":
                kinds = [
                    s.get("type")
                    for s in (value or [])
                    if isinstance(s, dict)
                ]
                print(f"  {etype}.stream -> {kinds}")
                continue
            text = json.dumps(value, ensure_ascii=False, default=str)
            print(f"  {etype}.{key} = {text[:220]}")


main()