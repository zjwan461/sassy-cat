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
    age: Optional[int] = Field(
        default=None, description="主人的年龄（整数），如 28。未知时省略此字段"
    )
    gender: Optional[str] = Field(
        default=None, description="主人的性别，如'男'、'女'。未知时省略此字段"
    )
    occupation: Optional[str] = Field(
        default=None, description="主人的职业/行业，如'软件工程师'、'在校学生'。未知时省略此字段"
    )
    location: Optional[str] = Field(
        default=None, description="主人所在城市/地区，如'杭州'、'上海浦东'。未知时省略此字段"
    )
    relationship_status: Optional[str] = Field(
        default=None,
        description="主人的情感/婚姻状况，如'单身'、'已婚'、'有对象'。未知时省略此字段",
    )
    personality: List[str] = Field(
        default_factory=list,
        description="主人的性格特点（长期特质，如'内向'、'急性子'）。保留已有条目并追加新条目",
    )
    important_dates: List[str] = Field(
        default_factory=list,
        description="主人重要的日期及其含义（如'5月20日生日'、'10月1日结婚纪念日'）。保留已有条目并追加新条目",
    )
    goals: List[str] = Field(
        default_factory=list,
        description="主人的目标/愿望（如'想减肥'、'准备考研'）。保留已有条目并追加新条目",
    )
    health_notes: Optional[str] = Field(
        default=None,
        description="主人的健康状况或需要注意的事项，如'对花生过敏'、'有慢性胃炎'。未知时省略此字段",
    )
