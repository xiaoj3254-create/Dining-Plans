from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class TeamMemberEvent(Base):
    """成员进出流水（真正的"历史留痕"）。

    TeamMember 表只用一行表达"当前状态"（复活式重加入会覆盖 left_at），
    因此多次进出的轨迹必须靠本表还原：风控复盘 / 纠纷仲裁 / 举报取证都要用到。
    action: joined / left / kicked / rejoined
    """

    __tablename__ = "team_member_events"
    __table_args__ = (Index("ix_tme_team_user", "team_id", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(10), nullable=False)
    operator_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 操作者（踢人=队长，退出=本人）
    note: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
