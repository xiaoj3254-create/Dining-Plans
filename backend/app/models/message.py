from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Message(Base):
    """群聊消息。一个队伍一个群（team_id 即群标识），成团后开放"""

    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_team_created", "team_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False, index=True)
    sender_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)  # system 消息为空
    # text / system / image（image 的 content 是上传后的图片 URL）
    msg_type: Mapped[str] = mapped_column(String(10), nullable=False, default="text")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # @全体成员：仅队长可置位，前端高亮展示
    mentions_all: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 撤回：误发敏感信息可补救（限发送后 2 分钟内，且仅本人）
    recalled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
