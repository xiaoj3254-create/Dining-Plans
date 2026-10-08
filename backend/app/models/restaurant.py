from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Restaurant(Base):
    """餐馆参考数据：队长发起组队时选定，作为统一就餐消费基准"""

    __tablename__ = "restaurants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    cuisine_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)  # 与广场菜系筛选项对齐
    district: Mapped[str | None] = mapped_column(String(50), nullable=True)  # 商圈
    avg_price: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)  # 人均（元）
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # 地理位置：用于广场「距离」标签、距离排序与半径筛选。
    # 只下发到客户端，由客户端用自身定位算距离 —— 用户的坐标不必上传服务端。
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    # 仅存文件名（如 hotpot_01.png）：出站时由 serializers 补 /static/food/ 前缀（小程序包内路径）
    image: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now
    )
