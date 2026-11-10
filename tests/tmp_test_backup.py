# -*- coding: utf-8 -*-
"""数据备份回归：配置/消息库/向量库/上传文件/技能库导出，拒绝备份到数据目录内。

运行：.venv\\Scripts\\python.exe tests\\tmp_test_backup.py
"""

import asyncio
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "python")))

from server import backup_api
from server.backup_api import ExportPayload, export_backup

FAILED = []


def check(name, cond, detail=""):
    print(("[PASS] " if cond else "[FAIL] ") + name + (f"  | {detail}" if detail else ""))
    if not cond:
        FAILED.append(name)


def main():
    with tempfile.TemporaryDirectory() as root:
        data = os.path.join(root, "data")
        skills = os.path.join(root, "skills")
        out = os.path.join(root, "out")
        for d in (data, skills, out):
            os.makedirs(d, exist_ok=True)

        con = sqlite3.connect(os.path.join(data, "messages.sqlite"))
        con.execute("create table t (id integer)")
        con.execute("insert into t values (1)")
        con.commit()
        con.close()
        os.makedirs(os.path.join(data, "chroma"))
        with open(os.path.join(data, "chroma", "a.bin"), "wb") as f:
            f.write(b"1234")
        os.makedirs(os.path.join(data, "upload", "rag"))
        with open(os.path.join(data, "upload", "rag", "x.txt"), "w", encoding="utf-8") as f:
            f.write("hi")
        with open(os.path.join(data, "config.user.json"), "w", encoding="utf-8") as f:
            f.write('{"a":1}')
        with open(os.path.join(skills, "S.md"), "w", encoding="utf-8") as f:
            f.write("s")

        old_data_dir = backup_api.paths.data_dir
        old_skills = backup_api.SKILLS_DIR
        try:
            backup_api.paths.data_dir = lambda: data
            backup_api.SKILLS_DIR = skills
            result = asyncio.run(export_backup(ExportPayload(targetDir=out)))
            dest = result["path"]
            names = {i["name"] for i in result["items"]}
            check("生成备份目录", os.path.isdir(dest), dest)
            check("包含配置", "config.user.json" in names)
            check("包含消息库", os.path.isfile(os.path.join(dest, "messages.sqlite")))
            check("包含向量库", os.path.isfile(os.path.join(dest, "chroma", "a.bin")))
            check("包含上传文件", os.path.isfile(os.path.join(dest, "upload", "rag", "x.txt")))
            check("包含技能库", os.path.isfile(os.path.join(dest, "skills", "S.md")))
            check("排除 checkpoints", not os.path.exists(os.path.join(dest, "checkpoints.sqlite")))
            check("README 存在", os.path.isfile(os.path.join(dest, "README.txt")))

            try:
                asyncio.run(export_backup(ExportPayload(targetDir=data)))
                check("拒绝备份到数据目录内", False)
            except Exception as e:
                check("拒绝备份到数据目录内", "不能放在应用数据目录内部" in str(e), str(e)[:80])
        finally:
            backup_api.paths.data_dir = old_data_dir
            backup_api.SKILLS_DIR = old_skills

    print("FAILED:", FAILED)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
