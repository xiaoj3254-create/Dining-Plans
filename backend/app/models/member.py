from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class TeamMember(Base):
    """队伍成员。历史留痕：退出/被踢不改行、只改 status；
    重新加入时将旧行"复活"为 active（UNIQUE(team_id,user_id) 保证一人一行）"""

    __tablename__ = "team_members"
    __table_args__ = (UniqueConstraint("team_id", "user_id", name="uq_member_team_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(8), nullable=False, default="member")  # leader / member
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="active")  # active/left/kicked
    joined_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    left_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
