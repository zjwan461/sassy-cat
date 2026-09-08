import os

import paths

# agent sandbox 工作目录（skills 加载、脚本执行），用户数据不放这里
WORK_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../..", "runtime"))
print(f"工作目录：{WORK_DIR}")

# checkpoint 属于用户数据，存放于 userData 目录（paths 解析，Electron 传入或跨平台兜底）
DB_URL = paths.data_path("checkpoints.sqlite")

SKILLS_DIR = "/skills"

USER_ID = "master"