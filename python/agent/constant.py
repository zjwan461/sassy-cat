import os

WORK_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../..", "runtime"))
print(f"工作目录：{WORK_DIR}")

DB_URL = f"{WORK_DIR}/checkpoints.sqlite"

SKILLS_DIR = "/skills"
