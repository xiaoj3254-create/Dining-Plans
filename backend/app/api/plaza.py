from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_verified
from app.models.user import User
from app.services import plaza_service

router = APIRouter(prefix="/api/plaza", tags=["plaza"])


@router.get("/teams")
def plaza_teams(
    cuisine: str | None = Query(None, description="菜系，支持逗号分隔多选，如 火锅,烧烤"),
    mode: str | None = None,
    keyword: str | None = None,
    meal_period: str | None = Query(
        None, description="用餐时段，支持逗号分隔多选：lunch,dinner"
    ),
    lat: float | None = Query(None, ge=-90, le=90, description="客户端纬度；不传则不返回距离"),
    lng: float | None = Query(None, ge=-180, le=180),
    max_distance_km: float | None = Query(None, gt=0, le=50),
    sort: str = Query("time", pattern="^(time|distance)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    user: User = Depends(require_verified),
    db: Session = Depends(get_db),
):
    """约饭广场。用户坐标只在本次请求内参与距离计算，不落库。"""
    return plaza_service.list_plaza(
        db, cuisine, mode, keyword, page, page_size, viewer_id=user.id,
        meal_period=meal_period, lat=lat, lng=lng,
        max_distance_km=max_distance_km, sort=sort,
    )
