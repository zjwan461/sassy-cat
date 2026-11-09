import logging
import os

import paths

logger = logging.getLogger(__name__)

# 应用内部数据目录（技能库、todo、dsh home、预览等）。
# 注意：这不是「工作区」——用户可在设置页另选工作区（见 agent/workspace.py），
# 文件工具与 shell 默认落在工作区，而内部数据始终留在应用目录下。
WORK_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../..", "runtime"))
RUNTIME_DIR = WORK_DIR

# 技能根目录（真实路径，与 skills_api / create_skill 共用，不随工作区变化）
SKILLS_DIR = os.path.join(WORK_DIR, "skills")

# checkpoint 属于用户数据，存放于 userData 目录（paths 解析，Electron 传入或跨平台兜底）
DB_URL = paths.data_path("checkpoints.sqlite")

USER_ID = "master"

logger.debug("agent 应用数据目录：%s", WORK_DIR)
