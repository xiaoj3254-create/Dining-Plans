from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.core.idcard import MIN_AGE
from app.core.timeutil import to_local_naive

# 年龄门槛：18 岁以下不得参与陌生人线下拼桌（原实现 gt=0，1 岁即可注册）
_AGE_FIELD = Field(ge=MIN_AGE, le=110)


class RegisterIn(BaseModel):
    username: str = Field(min_length=2, max_length=50)
    password: str = Field(min_length=6, max_length=64)
    nickname: str = Field(min_length=1, max_length=30)
    age: int = _AGE_FIELD
    gender: str = Field(pattern="^(male|female|other)$")
    # 是否已同意《用户服务协议》《隐私政策》；未同意不允许注册
    consent: bool = False


class LoginIn(BaseModel):
    username: str
    password: str


class AlipayLoginIn(BaseModel):
    code: str  # MVP mock 格式：mock:<username>
    nickname: str | None = Field(default=None, max_length=30)
    age: int | None = Field(default=None, ge=MIN_AGE, le=110)
    gender: str | None = Field(default=None, pattern="^(male|female|other)$")
    consent: bool = False


class ConsentIn(BaseModel):
    """首启同意门：记录用户同意的协议版本。"""

    version: str = Field(min_length=1, max_length=20)


class ProfileIn(BaseModel):
    nickname: str | None = Field(default=None, min_length=1, max_length=30)
    age: int | None = Field(default=None, ge=MIN_AGE, le=110)
    gender: str | None = Field(default=None, pattern="^(male|female|other)$")


class RealnameIn(BaseModel):
    real_name: str = Field(min_length=2, max_length=30)
    id_card: str = Field(min_length=18, max_length=18)
    # 敏感个人信息需单独同意，后端强制校验并在库中留痕版本号
    consent: bool = False


class TeamCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    mode: str = Field(pattern="^(anonymous|invite)$")
    target_size: int | None = Field(default=None, ge=2, le=20)
    cuisine_type: str | None = Field(default=None, max_length=30)
    menu_summary: str | None = Field(default=None, max_length=500)
    dining_time: datetime | None = None
    location_hint: str | None = Field(default=None, max_length=100)
    restaurant_id: int | None = Field(default=None, ge=1)  # 选定餐馆（发布必填）
    dish_ids: list[int] | None = Field(default=None, max_length=20)  # 预选菜品（选填）

    @field_validator("dining_time")
    @classmethod
    def _norm_dining_time(cls, v: datetime | None) -> datetime | None:
        """客户端时间统一归一到服务端配置时区的 naive 本地时间。"""
        return to_local_naive(v)


class TeamUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=50)
    mode: str | None = Field(default=None, pattern="^(anonymous|invite)$")
    target_size: int | None = Field(default=None, ge=2, le=20)
    cuisine_type: str | None = Field(default=None, max_length=30)
    menu_summary: str | None = Field(default=None, max_length=500)
    dining_time: datetime | None = None
    location_hint: str | None = Field(default=None, max_length=100)
    restaurant_id: int | None = Field(default=None, ge=1)
    dish_ids: list[int] | None = Field(default=None, max_length=20)

    @field_validator("dining_time")
    @classmethod
    def _norm_dining_time(cls, v: datetime | None) -> datetime | None:
        return to_local_naive(v)


class JoinByLinkIn(BaseModel):
    code: str = Field(min_length=1, max_length=32)


class CheckinIn(BaseModel):
    checkin_code: str = Field(min_length=1, max_length=32)


class BillIn(BaseModel):
    """金额用 Decimal：float 参与分账会引入分位误差。"""

    total_amount: Decimal = Field(gt=0, le=Decimal("1000000"), decimal_places=2)


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=500)
    # text：正常文本；image：上传接口返回的站内图片路径
    msg_type: str = Field(default="text", pattern="^(text|image)$")
    # @全体成员（仅队长有效，服务端二次校验）
    mentions_all: bool = False

    @field_validator("content")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        text = (v or "").strip()
        if not text:
            raise ValueError("消息内容不能为空")
        return text


class ReportIn(BaseModel):
    target_user_id: int = Field(ge=1)
    team_id: int | None = Field(default=None, ge=1)
    message_id: int | None = Field(default=None, ge=1)
    reason: str = Field(pattern="^(harassment|fraud|abuse|illegal|other)$")
    detail: str | None = Field(default=None, max_length=200)


class BlockIn(BaseModel):
    target_user_id: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=100)
