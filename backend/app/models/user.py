from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)  # 支付宝登录用户可为空
    alipay_user_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)

    # 展示信息（脱敏后对外仅暴露 nickname/age/gender）
    nickname: Mapped[str] = mapped_column(String(30), nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    gender: Mapped[str] = mapped_column(String(10), nullable=False, default="other")

    # 实名登记（MVP：本地格式校验 + 带盐摘要留痕；未接入权威核验源，见 settings.REALNAME_MODE）
    real_name_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    real_name_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    id_card_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # 从证件号解析出的出生日期 YYYY-MM-DD：用于阻止"实名后改年龄绕过年龄门槛"
    birth_date: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # 个人信息处理同意留痕（PIPL：敏感信息需单独同意 + 可回溯的版本号）
    consent_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    consent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    realname_consent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # 举报累计触发的行为限制
    report_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    restricted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    restricted_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # 注销软删（保留队伍结构，个人信息匿名化）
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # JWT 版本号：注销/强制下线时 +1，旧 token 立即失效
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
