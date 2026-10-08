from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class PushOutbox(Base):
    """小程序订阅消息待发队列（outbox）。

    站内红点只能在用户主动进入小程序时被看到；成团 / 账单生效 / 核销提醒
    这类强时效事件必须能推到支付宝小程序订阅消息。真实推送依赖正式 AppID
    与模板 ID，因此在拿到凭据前：先按"落库排队"的方式把意图固化下来，
    provider 落地后由 worker 消费即可，业务代码无需再改。

    status: pending(待发) / sent(已发) / failed(失败) / skipped(未授权或无模板)
    """

    __tablename__ = "push_outbox"
    __table_args__ = (
        Index("ix_push_status", "status", "created_at"),
        Index("ix_push_user_scene", "user_id", "scene"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    scene: Mapped[str] = mapped_column(String(30), nullable=False)  # formed / bill_effective / checkin_reminder
    template_data: Mapped[str] = mapped_column(Text, nullable=False, default="{}")  # JSON
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="pending")
    error: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
