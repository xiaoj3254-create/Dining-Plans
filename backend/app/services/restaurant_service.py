"""餐馆与菜品查询服务（参考数据，只读）。"""

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.dish import Dish
from app.models.restaurant import Restaurant
from app.schemas.serializers import dish_out, restaurant_out


def list_restaurants(db: Session, cuisine: str | None, keyword: str | None,
                     page: int, page_size: int) -> dict:
    """餐馆列表：支持菜系筛选与关键词（名称/菜系/商圈）"""
    conds = [Restaurant.is_active.is_(True)]
    if cuisine:
        conds.append(Restaurant.cuisine_type.contains(cuisine))
    if keyword:
        kw = keyword.strip()
        if kw:
            conds.append(or_(
                Restaurant.name.contains(kw),
                Restaurant.cuisine_type.contains(kw),
                Restaurant.district.contains(kw),
            ))
    total = db.execute(
        select(func.count()).select_from(Restaurant).where(*conds)
    ).scalar() or 0
    rows = db.execute(
        select(Restaurant).where(*conds)
        .order_by(Restaurant.sort_order, Restaurant.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).scalars().all()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "restaurants": [restaurant_out(db, r) for r in rows],
    }


def get_restaurant(db: Session, restaurant_id: int, with_dishes: bool = True) -> dict:
    r = db.get(Restaurant, restaurant_id)
    if r is None or not r.is_active:
        raise HTTPException(status_code=404, detail="餐馆不存在")
    return restaurant_out(db, r, with_dishes=with_dishes)


def list_dishes_of(db: Session, restaurant_id: int, category: str | None,
                   keyword: str | None) -> dict:
    r = db.get(Restaurant, restaurant_id)
    if r is None or not r.is_active:
        raise HTTPException(status_code=404, detail="餐馆不存在")
    conds = [Dish.restaurant_id == restaurant_id, Dish.is_active.is_(True)]
    if category:
        conds.append(Dish.category == category)
    if keyword:
        kw = keyword.strip()
        if kw:
            conds.append(or_(Dish.name.contains(kw), Dish.tags.contains(kw)))
    rows = db.execute(
        select(Dish).where(*conds).order_by(Dish.sort_order, Dish.id)
    ).scalars().all()
    return {
        "restaurant_id": restaurant_id,
        "restaurant_name": r.name,
        "total": len(rows),
        "dishes": [dish_out(d) for d in rows],
    }
