from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Checkin(Base):
    """到场确认记录。成团时为每名成员预生成核销码，本人确认到场时使用。

    语义：MVP 中核销 = 本人确认到场（非商家扫码），因此码只对本人可见。
    账单生效后核销窗口关闭（防止锁账后补核销白吃）。
    """

    __tablename__ = "checkins"
    __table_args__ = (
        UniqueConstraint("team_id", "user_id", name="uq_checkin_team_user"),
        Index("uq_checkin_code", "checkin_code", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    checkin_code: Mapped[str] = mapped_column(String(32), nullable=False)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # NULL=未到场
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
