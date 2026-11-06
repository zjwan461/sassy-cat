import logging
import os

import paths

logger = logging.getLogger(__name__)

# agent 工作目录（skills 加载、脚本执行），用户数据不放这里
WORK_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../..", "runtime"))

# 技能根目录（真实路径，与 skills_api / create_skill 共用）
SKILLS_DIR = os.path.join(WORK_DIR, "skills")

# checkpoint 属于用户数据，存放于 userData 目录（paths 解析，Electron 传入或跨平台兜底）
DB_URL = paths.data_path("checkpoints.sqlite")

USER_ID = "master"

logger.debug("agent 工作目录：%s", WORK_DIR)
