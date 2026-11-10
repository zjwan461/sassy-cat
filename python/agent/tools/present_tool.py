# -*- coding: utf-8 -*-
"""present 工具：把本轮新建/修改的文件以卡片形式展示给用户。

为什么需要它
------------
Agent 在任务结束时通常只用一句话总结“改好了”，但用户真正想看的是**改了哪些文件**。
DSH 的 present 工具会在回答里生成一张文件卡片，这里按同样的交互补齐：

- 只展示文件，不复制/移动文件；
- 路径统一按当前工作区解析，越界或不存在直接跳过并回传原因；
- 附带行数、大小，工作区是 git 仓库时再附带 `+added / -removed`；
- 返回结构化 JSON，前端按 `type=present` 渲染文件卡片，历史消息同样可还原。
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from langchain.tools import tool

from agent.workspace import resolve_workspace

MAX_FILES = 20
MAX_TEXT_BYTES = 5 * 1024 * 1024


def _count_lines(path: Path) -> int:
    """统计文本行数；二进制/超大文件返回 0。"""
    try:
        if path.stat().st_size > MAX_TEXT_BYTES:
            return 0
        with open(path, "rb") as f:
            chunk = f.read(4096)
            if b"\x00" in chunk:
                return 0
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def _git_stats(root: Path, target: Path, lines: int) -> dict[str, Any]:
    """工作区在 git 仓库内时，读取该文件的变更状态与增删行数。"""
    try:
        rel = target.relative_to(root).as_posix()
        status = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain", "--", rel],
            capture_output=True, text=True, timeout=3,
        )
        if status.returncode != 0:
            return {}
        status_line = (status.stdout or "").strip()
        if status_line.startswith("??") or status_line.startswith("A"):
            change = "added"
        elif status_line:
            change = "modified"
        else:
            # git 仓库里被 ignore / 尚未加入索引的文件，status 可能为空；
            # 用 ls-files 判断是否已跟踪，未跟踪就按新增统计行数。
            tracked = subprocess.run(
                ["git", "-C", str(root), "ls-files", "--error-unmatch", rel],
                capture_output=True, text=True, timeout=3,
            )
            change = "unknown" if tracked.returncode == 0 else "added"

        diff = subprocess.run(
            ["git", "-C", str(root), "diff", "--numstat", "--", rel],
            capture_output=True, text=True, timeout=3,
        )
        added = removed = None
        output = (diff.stdout or "").strip()
        if output:
            parts = output.split("\t")
            if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                added, removed = int(parts[0]), int(parts[1])
        elif change == "added":
            added, removed = lines, 0
        return {"change": change, "added": added, "removed": removed}
    except (OSError, subprocess.SubprocessError, ValueError):
        return {}


@tool(description="把本轮新建或修改的文件展示给用户（聊天中渲染文件卡片）。")
def present(files: list[str] | str, title: str = "", summary: str = "") -> str:
    """展示本轮产出/修改的文件。

    触发场景：只要本轮用 write_file / edit_file 新建或修改了文件，**收尾时必须调用**
    本工具，把相关文件展示给主人；纯问答、只读检索、只运行命令且未改文件时不要调用。

    参数：
    - files: 文件路径列表（相对当前工作区；也接受绝对路径，但必须在工作区内）。
      一次最多 20 个，超出部分会忽略。
    - title: 卡片标题，留空时自动生成「本轮产出 N 个文件」。
    - summary: 可选的一句话说明。

    返回：结构化 JSON（type=present），前端据此渲染文件卡片。
    """
    root = Path(resolve_workspace()).resolve()
    raw_files = [files] if isinstance(files, str) else list(files or [])
    raw_files = [str(f).strip() for f in raw_files if str(f).strip()]
    if not raw_files:
        return "未提供要展示的文件路径。"

    items: list[dict[str, Any]] = []
    skipped: list[str] = []
    seen: set[str] = set()

    for raw in raw_files[:MAX_FILES]:
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = root / candidate
        try:
            target = candidate.resolve()
            target.relative_to(root)
        except (OSError, ValueError):
            skipped.append(f"{raw}（不在工作区内）")
            continue
        if not target.is_file():
            skipped.append(f"{raw}（文件不存在）")
            continue
        key = str(target).lower() if os.name == "nt" else str(target)
        if key in seen:
            continue
        seen.add(key)

        stat = target.stat()
        lines = _count_lines(target)
        item: dict[str, Any] = {
            "name": target.name,
            "path": target.relative_to(root).as_posix(),
            "absolute": str(target),
            "ext": target.suffix.lower().lstrip("."),
            "size": stat.st_size,
            "lines": lines,
            "change": "unknown",
            "added": None,
            "removed": None,
        }
        item.update(_git_stats(root, target, lines))
        items.append(item)

    if not items:
        detail = "；".join(skipped[:3])
        return f"没有可展示的文件。{detail}" if detail else "没有可展示的文件。"

    total_added = sum(int(f["added"] or 0) for f in items)
    total_removed = sum(int(f["removed"] or 0) for f in items)
    payload = {
        "type": "present",
        "title": (title or "").strip() or f"本轮产出 {len(items)} 个文件",
        "summary": (summary or "").strip(),
        "files": items,
        "totalAdded": total_added,
        "totalRemoved": total_removed,
        "skipped": skipped[:5],
    }
    return json.dumps(payload, ensure_ascii=False)


__all__ = ["present"]
