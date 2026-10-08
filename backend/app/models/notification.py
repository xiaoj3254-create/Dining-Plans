from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Notification(Base):
    """站内通知。

    类型：member_joined / member_left / kicked / formed / bill_effective /
    team_failed / team_completed / checkin_reminder / report_result
    """

    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_user_read", "user_id", "is_read"),
        # 幂等判定与"按队伍聚合"都依赖结构化 team_id，不再解析 payload 文本
        Index("ix_notifications_user_type_team", "user_id", "type", "team_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    # 关联队伍（无关联的通知为 NULL）；payload 保留展示所需的冗余字段
    team_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False, default="{}")  # JSON
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
