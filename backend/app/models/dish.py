from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Dish(Base):
    """餐馆菜品：队长可提前勾选，形成队伍的预选菜单（价格/名称会快照到队伍上）"""

    __tablename__ = "dishes"
    __table_args__ = (UniqueConstraint("restaurant_id", "name", name="uq_dishes_rest_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    restaurant_id: Mapped[int] = mapped_column(
        ForeignKey("restaurants.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)  # 元，2 位小数
    category: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)  # 荤菜/素菜/主食/汤/点心…
    tags: Mapped[str | None] = mapped_column(String(50), nullable=True)  # 逗号分隔：招牌,必点,辣
    image: Mapped[str | None] = mapped_column(String(120), nullable=True)  # 仅存文件名，同 Restaurant.image
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
