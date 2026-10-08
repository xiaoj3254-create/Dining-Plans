from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Bill(Base):
    """账单。一队一单；pending(未锁定)→locked(核销窗口关闭后生效)→settled(全员结清)；void(异常作废)

    金额注解统一为 Decimal：列类型是 NUMERIC(10,2)，SQLAlchemy 返回的也是 Decimal，
    注解写成 float 会诱导调用方做浮点算术，分账时产生分位误差。
    """

    __tablename__ = "bills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False, unique=True)
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)  # 队长录入，可后录
    per_capita: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)  # 生效时锁定快照
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="pending")
    effective_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
