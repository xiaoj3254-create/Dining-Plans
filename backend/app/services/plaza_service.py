"""约饭广场：仅招募中的队伍。

能力（2026-10-08 体验优化）：
- 硬过滤：就餐时间必须仍在未来（过期队伍即便未被巡检收口也不出现在广场）；
- 拉黑过滤：与我有拉黑关系（任一方向）的队长，其队伍不出现在我的广场；
- 筛选多选：`cuisine` 与 `meal_period` 均支持**逗号分隔多值**，维度内取并集（OR）：

  - `cuisine=火锅,烧烤` → 命中任一菜系即可（用于"同时想看火锅和烧烤"）；
  - `meal_period=lunch,dinner` → 合并时段区间（午市 11:00–14:59 / 晚市 16:00–21:59）。
- 用餐时段：`meal_period=lunch|dinner`（午市 11:00–14:59 / 晚市 16:00–21:59）；
- 距离：客户端上报自身坐标（`lat`/`lng`）后，服务端计算 `distance_km`、支持半径过滤
  与按距离排序。**用户坐标不落库**，只在本次请求内参与计算。

规模说明：为支持"按距离排序 + 分页"的正确性，距离相关查询会把候选集（上限
`_MAX_SCAN` 条）取回内存排序后再分页。当前数据规模（十几家餐馆、数十支队伍）绰绰有余；
若将来队伍量级上到万级，应改为在 DB 侧维护经纬度并接入支持空间索引的数据库。
"""

import math

from fastapi import HTTPException
from sqlalchemy import Integer, and_, func, or_, select
from sqlalchemy.orm import Session

from app.agent.states import TeamStatus
from app.core.timeutil import now
from app.models.restaurant import Restaurant
from app.models.team import Team
from app.schemas.serializers import team_card

# 用餐时段 → (起始小时, 结束小时)，左闭右开
MEAL_PERIODS = {"lunch": (11, 15), "dinner": (16, 22)}
MAX_DISTANCE_FILTERS = (1.0, 2.0, 3.0, 5.0, 10.0)
_MAX_SCAN = 500


def _split_multi(value: str | None) -> list[str]:
    """把 `a,b,c` 形式的筛选参数拆成去空、去重的列表（支持多选筛选）。

    单值（`火锅`）与多值（`火锅,烧烤`）走同一路径，因此保持向后兼容。
    """
    if not value:
        return []
    out: list[str] = []
    for piece in str(value).split(","):
        name = piece.strip()
        if name and name not in out:
            out.append(name)
    return out


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """两点球面距离（km）。"""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _distance_of(team, lat: float | None, lng: float | None, cache: dict) -> float | None:
    """队伍 → 距离（km）。无餐馆坐标或无用户坐标时返回 None。"""
    if lat is None or lng is None or not team.restaurant_id:
        return None
    if team.restaurant_id not in cache:
        r = cache["_db"].get(Restaurant, team.restaurant_id)
        cache[team.restaurant_id] = (
            (float(r.latitude), float(r.longitude))
            if r is not None and r.latitude is not None and r.longitude is not None
            else None
        )
    point = cache[team.restaurant_id]
    if point is None:
        return None
    return round(haversine_km(lat, lng, point[0], point[1]), 2)


def list_plaza(db: Session, cuisine: str | None, mode: str | None, keyword: str | None,
               page: int, page_size: int, viewer_id: int | None = None,
               meal_period: str | None = None, lat: float | None = None,
               lng: float | None = None, max_distance_km: float | None = None,
               sort: str = "time") -> dict:
    conds = [
        Team.status == TeamStatus.RECRUITING.value,
        Team.dining_time.is_not(None),
        Team.dining_time > now(),
    ]
    # 拉黑过滤：与我有拉黑关系（任一方向）的队长，其队伍不出现在我的广场
    if viewer_id is not None:
        from app.services.report_service import blocked_ids

        hidden = blocked_ids(db, viewer_id)
        if hidden:
            conds.append(Team.leader_id.notin_(hidden))
    if cuisine:
        names = _split_multi(cuisine)
        if names:
            # 维度内取并集：命中任一菜系即可（"火锅,烧烤"→ 两种都想要）
            conds.append(or_(*[Team.cuisine_type.contains(n) for n in names]))
    if mode:
        conds.append(Team.mode == mode)
    raw_periods = _split_multi(meal_period)
    if raw_periods:
        periods = [p for p in raw_periods if p in MEAL_PERIODS]
        if not periods:
            # 全部取值非法才拒绝；部分合法时取合法部分（宽进）
            raise HTTPException(status_code=422, detail="用餐时段取值不合法")
        # SQLite 的 strftime 直接作用于 DATETIME 文本列
        hour = func.cast(func.strftime("%H", Team.dining_time), Integer)
        conds.append(or_(*[and_(hour >= MEAL_PERIODS[p][0], hour < MEAL_PERIODS[p][1])
                           for p in periods]))
    if keyword:
        kw = keyword.strip()
        if kw:
            conds.append(
                or_(
                    Team.name.contains(kw),
                    Team.cuisine_type.contains(kw),
                    Team.location_hint.contains(kw),
                    Team.menu_summary.contains(kw),
                    Restaurant.name.contains(kw),  # 关键词也命中餐馆名
                    Restaurant.district.contains(kw),
                )
            )

    # 1 队 1 店，outerjoin 不会放大行数
    joined = select(Team).outerjoin(Restaurant, Team.restaurant_id == Restaurant.id)
    rows = db.execute(
        joined.where(*conds).order_by(Team.dining_time.asc()).limit(_MAX_SCAN)
    ).scalars().all()

    # 距离：算距离 → 半径过滤 → 可选排序（用户坐标不落库，仅本次请求内使用）
    dist_cache: dict = {"_db": db}
    with_distance: list[tuple] = []
    for t in rows:
        d = _distance_of(t, lat, lng, dist_cache)
        if max_distance_km is not None and d is not None and d > max_distance_km:
            continue
        with_distance.append((t, d))

    if sort == "distance" and lat is not None and lng is not None:
        # 有距离的按距离升序在前，无坐标的排最后（仍按就餐时间）
        with_distance.sort(key=lambda pair: (pair[1] is None, pair[1] or 0.0, pair[0].dining_time))

    total = len(with_distance)
    start = (page - 1) * page_size
    page_rows = with_distance[start:start + page_size]

    teams = []
    for t, d in page_rows:
        card = team_card(db, t)
        card["distance_km"] = d
        teams.append(card)

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_more": start + len(page_rows) < total,
        "sort": sort if (sort == "distance" and lat is not None) else "time",
        "teams": teams,
    }
