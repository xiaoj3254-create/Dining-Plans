from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Payment(Base):
    """人均独立结算记录。账单锁定时按成员批量生成，各自独立支付、互不垫付"""

    __tablename__ = "payments"
    __table_args__ = (UniqueConstraint("bill_id", "user_id", name="uq_payment_bill_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bill_id: Mapped[int] = mapped_column(ForeignKey("bills.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    # unpaid / paid。
    # 注意：MVP 不需要 refunded —— 队伍终止（ABORT）的守卫 g_abort_allowed 已禁止
    # "已有成功支付"时终止，因此不存在"已付款却要退款"的路径。
    # 将来若开放退款（如商家取消），需新增 refunded 状态 + 退款流水 + 幂等键。
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="unpaid")
    mock_txn_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
