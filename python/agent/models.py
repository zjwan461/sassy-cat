from typing import Any, List, Optional, Dict
from pydantic import BaseModel, Field


# ====================== 数据模型 ======================
class OwnerProfile(BaseModel):
    """主人核心画像。整体覆盖写入，须合并 [主人画像] 已有信息与本轮新信息后完整提交。"""

    master_name: Optional[str] = Field(
        default=None, description="主人的姓名/称呼，如'小明'、'老王'。未知时省略此字段"
    )
    dislikes: List[str] = Field(
        default_factory=list,
        description="主人不喜欢的话题/事物（长期偏好，如'香菜'、'噪音'）。保留已有条目并追加新条目",
    )
    likes: List[str] = Field(
        default_factory=list,
        description="主人的爱好（长期偏好，如'打篮球'、'喝奶茶'）。保留已有条目并追加新条目",
    )
    daily_habit: Optional[str] = Field(
        default=None, description="主人作息习惯，如'经常熬夜'、'每天六点晨跑'。未知时省略此字段"
    )
