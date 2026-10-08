from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_verified
from app.models.user import User
from app.services import restaurant_service

router = APIRouter(prefix="/api/restaurants", tags=["restaurants"])


@router.get("")
def list_restaurants(
    cuisine: str | None = None,
    keyword: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    user: User = Depends(require_verified),
    db: Session = Depends(get_db),
):
    """餐馆列表：菜系筛选 + 关键词搜索（名称/菜系/商圈）"""
    return restaurant_service.list_restaurants(db, cuisine, keyword, page, page_size)


@router.get("/{restaurant_id}")
def get_restaurant(
    restaurant_id: int,
    user: User = Depends(require_verified),
    db: Session = Depends(get_db),
):
    """餐馆详情（含全部菜品）"""
    return restaurant_service.get_restaurant(db, restaurant_id, with_dishes=True)


@router.get("/{restaurant_id}/dishes")
def list_dishes(
    restaurant_id: int,
    category: str | None = None,
    keyword: str | None = None,
    user: User = Depends(require_verified),
    db: Session = Depends(get_db),
):
    """该餐馆菜品清单（可按分类 / 关键词过滤）"""
    return restaurant_service.list_dishes_of(db, restaurant_id, category, keyword)
