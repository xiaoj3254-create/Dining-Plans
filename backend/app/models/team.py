from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str | None] = mapped_column(String(16), unique=True, nullable=True)  # 邀请码（模式二）
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    mode: Mapped[str] = mapped_column(String(10), nullable=False)  # anonymous / invite
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="draft", index=True)

    # 草稿期允许为空（发布守卫强校验）；禁止再用哨兵值（datetime.max 之类）占位
    target_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_size: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    cuisine_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    menu_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON 快照 [{dish_id,name,price,image}]：由服务端按 dish_ids 重建，含选菜时的价格
    menu_items: Mapped[str | None] = mapped_column(Text, nullable=True)
    dining_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    location_hint: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # 选定餐馆（草稿可空，发布时强校验）
    restaurant_id: Mapped[int | None] = mapped_column(
        ForeignKey("restaurants.id"), nullable=True, index=True
    )

    invite_open: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    leader_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 乐观锁

    formed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 失败归因：disbanded / checkin_aborted / expired
    failed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fail_reason: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now
    )

    __table_args__ = (
        # 冗余计数不变量下沉到 DB 层（草稿期允许 target_size 未设置）
        CheckConstraint(
            "target_size IS NULL OR current_size <= target_size", name="ck_teams_no_oversell"
        ),
        CheckConstraint("target_size IS NULL OR target_size >= 2", name="ck_teams_target_min"),
        CheckConstraint("current_size >= 0", name="ck_teams_size_nonneg"),
        Index("ix_teams_status_mode", "status", "mode"),
        Index("ix_teams_dining_time", "dining_time"),
        Index("ix_teams_status_dining", "status", "dining_time"),
        UniqueConstraint("code", name="uq_teams_code"),
    )
