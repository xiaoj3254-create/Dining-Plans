from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AuditLog(Base):
    """敏感操作审计日志（踢人 / 改账单 / 解散 / 实名 / 注销 / 限制）。

    只追加，不修改不删除；detail 存 JSON 摘要（脱敏后的前后值）。
    """

    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_actor", "actor_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    target_type: Mapped[str | None] = mapped_column(String(20), nullable=True)  # team / user / bill
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="{}")  # JSON，已脱敏
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
