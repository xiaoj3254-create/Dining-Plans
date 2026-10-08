"""序列化层：所有 API 出站数据的唯一出口。

隐私铁律 1：除 /api/auth/me、/api/users/me 外，任何响应中的用户形态都必须是
`user_public()`，即只含 nickname / age / gender，绝不含 username / real_name /
证件 / 手机号 / 哈希。

隐私铁律 2：非成员的详情视图只暴露 `profile` 概况（男女人数/平均年龄），
不返回 `members` 名单——避免未报名即可逐队收集成员昵称。
"""

import json
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.states import BillStatus, MemberStatus
from app.core.timeutil import iso
from app.models.bill import Bill
from app.models.checkin import Checkin
from app.models.dish import Dish
from app.models.member import TeamMember
from app.models.restaurant import Restaurant
from app.models.user import User

# 菜品/餐馆图片：DB 只存文件名，出站统一补小程序包内路径（必须带前导斜杠）
FOOD_PREFIX = "/static/food/"
DEFAULT_FOOD = FOOD_PREFIX + "_default.png"

__all__ = [
    "iso", "food_image", "user_public", "user_me", "profile_summary", "active_members",
    "dish_out", "restaurant_summary", "restaurant_out", "list_dishes", "parse_menu_items",
    "estimate", "team_card", "member_out", "team_detail", "message_out", "checkin_out",
    "notification_out",
]


def food_image(name: str | None) -> str:
    """图片出站路径：存文件名 → /static/food/<文件名>，缺图回退占位图"""
    return FOOD_PREFIX + name if name else DEFAULT_FOOD


def user_public(user: User) -> dict:
    """★ UserPublic：唯一对外用户形态"""
    return {"nickname": user.nickname, "age": user.age, "gender": user.gender}


def user_me(user: User) -> dict:
    """本人信息（允许包含 username 供自己查看，但绝不含证件/哈希）"""
    return {
        "id": user.id,
        "username": user.username,
        "nickname": user.nickname,
        "age": user.age,
        "gender": user.gender,
        "real_name_verified": user.real_name_verified,
        "consent_version": user.consent_version,
        "restricted": user.restricted_at is not None,
        "restricted_reason": user.restricted_reason,
    }


def profile_summary(db: Session, team) -> dict:
    """成员年龄性别概况，如 3男2女 / 平均26岁"""
    rows = (
        db.execute(
            select(User)
            .join(TeamMember, TeamMember.user_id == User.id)
            .where(TeamMember.team_id == team.id, TeamMember.status == MemberStatus.ACTIVE)
        )
        .scalars()
        .all()
    )
    male = sum(1 for u in rows if u.gender == "male")
    female = sum(1 for u in rows if u.gender == "female")
    other = len(rows) - male - female
    avg_age = round(sum(u.age for u in rows) / len(rows), 1) if rows else 0
    return {"male": male, "female": female, "other": other, "avg_age": avg_age, "count": len(rows)}


def active_members(db: Session, team) -> list[TeamMember]:
    return (
        db.execute(
            select(TeamMember).where(
                TeamMember.team_id == team.id, TeamMember.status == MemberStatus.ACTIVE
            )
        )
        .scalars()
        .all()
    )


def _remaining(team) -> int | None:
    """剩余名额：草稿期未设置目标人数时为 None（不再用 0 冒充）。"""
    if team.target_size is None:
        return None
    return team.target_size - team.current_size


# ---------- 餐馆 / 菜品 / 预选菜单 ----------

def dish_out(d: Dish) -> dict:
    """菜品出站（仅静态信息，无用户数据）"""
    return {
        "id": d.id,
        "name": d.name,
        "price": float(d.price),
        "category": d.category,
        "tags": d.tags,
        "image": food_image(d.image),
    }


def restaurant_summary(db: Session, team) -> dict | None:
    """广场卡片/详情用的餐馆轻量信息（含坐标，供客户端算距离）"""
    if not team.restaurant_id:
        return None
    r = db.get(Restaurant, team.restaurant_id)
    if r is None:
        return None
    return {
        "id": r.id,
        "name": r.name,
        "cuisine_type": r.cuisine_type,
        "district": r.district,
        "image": food_image(r.image),
        "latitude": float(r.latitude) if r.latitude is not None else None,
        "longitude": float(r.longitude) if r.longitude is not None else None,
    }


def restaurant_out(db: Session, restaurant: Restaurant, with_dishes: bool = False) -> dict:
    out = {
        "id": restaurant.id,
        "name": restaurant.name,
        "cuisine_type": restaurant.cuisine_type,
        "district": restaurant.district,
        "avg_price": float(restaurant.avg_price) if restaurant.avg_price is not None else None,
        "description": restaurant.description,
        "image": food_image(restaurant.image),
        "latitude": float(restaurant.latitude) if restaurant.latitude is not None else None,
        "longitude": float(restaurant.longitude) if restaurant.longitude is not None else None,
        "dish_count": len(list_dishes(db, restaurant.id)),
    }
    if with_dishes:
        out["dishes"] = [dish_out(d) for d in list_dishes(db, restaurant.id)]
    return out


def list_dishes(db: Session, restaurant_id: int) -> list[Dish]:
    return (
        db.execute(
            select(Dish)
            .where(Dish.restaurant_id == restaurant_id, Dish.is_active.is_(True))
            .order_by(Dish.sort_order, Dish.id)
        )
        .scalars()
        .all()
    )


def parse_menu_items(team) -> list[dict]:
    """队伍的预选菜单快照（服务端按 dish_ids 重建写入，含当时价格）"""
    if not team.menu_items:
        return []
    try:
        items = json.loads(team.menu_items)
    except Exception:
        return []
    return items if isinstance(items, list) else []


def estimate(team) -> dict:
    """预估消费：按满员计划人数分摊，仅供展示参考，不参与账单结算"""
    items = parse_menu_items(team)
    total = sum((Decimal(str(i.get("price") or 0)) for i in items), Decimal("0"))
    n = team.target_size or 0
    per = (total / n).quantize(Decimal("0.01")) if n else Decimal("0")
    return {"total": float(total), "per_capita": float(per), "dish_count": len(items)}


def recruit_deadline(team) -> datetime | None:
    """招募截止时间 = 就餐时间 + 招募宽限期（与巡检 EXPIRE 判定同一口径）。"""
    from datetime import timedelta

    from app.core.config import settings

    if team.dining_time is None or settings.RECRUITING_EXPIRE_GRACE_HOURS <= 0:
        return None
    return team.dining_time + timedelta(hours=settings.RECRUITING_EXPIRE_GRACE_HOURS)


def team_card(db: Session, team) -> dict:
    """广场卡片。

    额外提供 `recruit_deadline`（前端据此显示"剩余招募时长"）与 `restaurant.latitude/
    longitude`（前端据此算距离）；`distance_km` 由广场服务在拿到用户坐标后注入。
    """
    return {
        "id": team.id,
        "name": team.name,
        "mode": team.mode,
        "status": team.status,
        "cuisine_type": team.cuisine_type,
        "menu_summary": team.menu_summary,
        "dining_time": iso(team.dining_time),
        "recruit_deadline": iso(recruit_deadline(team)),
        "current_size": team.current_size,
        "target_size": team.target_size,
        "remaining": _remaining(team),
        "location_hint": team.location_hint,
        "restaurant": restaurant_summary(db, team),
        "profile": profile_summary(db, team),
        "created_at": iso(team.created_at),
    }


def member_out(db: Session, member: TeamMember, expose_id: bool = False) -> dict:
    """expose_id：对**同队成员**开放 user_id。

    用途：队长踢人、成员互相举报/拉黑都需要一个稳定的引用；纯数字 id 本身不属
    个人信息（平台没有公开用户主页端点），且只对已在同一队伍内的成员可见。
    对外部浏览者与成团队伍的非成员一律不输出。
    """
    user = db.get(User, member.user_id)
    out = {
        "user": user_public(user),
        "role": member.role,
        "joined_at": iso(member.joined_at),
    }
    if expose_id:
        out["user_id"] = member.user_id
    return out


def _bill_status(db: Session, team) -> str | None:
    row = db.execute(select(Bill).where(Bill.team_id == team.id)).scalar_one_or_none()
    return row.status if row else None


# 供服务层复用的公开别名（列表接口需要账单状态来决定能否退出/补位）
bill_status_of = _bill_status


def team_detail(db: Session, team, viewer_id: int) -> dict:
    members = active_members(db, team)
    # 成员按加入时间升序（joined_at 可能相同，用 id 兜底保证顺序稳定）
    members = sorted(members, key=lambda m: (m.joined_at, m.id))
    my = next((m for m in members if m.user_id == viewer_id), None)
    is_member = my is not None
    is_leader = viewer_id == team.leader_id
    bill_status = _bill_status(db, team)

    # 非成员（含未报名的浏览者）：只给成员概况，不给名单
    show_members = is_member
    return {
        "id": team.id,
        "name": team.name,
        "mode": team.mode,
        "status": team.status,
        "cuisine_type": team.cuisine_type,
        "menu_summary": team.menu_summary,
        "dining_time": iso(team.dining_time),
        "location_hint": team.location_hint,
        "restaurant": restaurant_summary(db, team),
        "dishes": parse_menu_items(team),
        "estimate": estimate(team),
        "current_size": team.current_size,
        "target_size": team.target_size,
        "remaining": _remaining(team),
        "invite_open": team.invite_open,
        "code": team.code if (is_member or is_leader) else None,
        "formed_at": iso(team.formed_at),
        "completed_at": iso(team.completed_at),
        "failed_at": iso(team.failed_at),
        "fail_reason": team.fail_reason,
        "created_at": iso(team.created_at),
        "profile": profile_summary(db, team),
        "members": (
            # 仅对同队成员输出名单；成员之间暴露 user_id 以便踢人/举报/拉黑
            [member_out(db, m, expose_id=True) for m in members]
            if show_members else []
        ),
        "members_hidden": not show_members,
        "my_role": my.role if my else None,
        "is_member": is_member,
        "bill_status": bill_status,
        # 成团后仅"账单尚未生效"阶段允许退出（见 (formed, leave) 流转）
        "can_leave": (
            bool(my and my.role != "leader" and team.status == "formed"
                 and bill_status in (None, BillStatus.PENDING))
            if team.status == "formed" else bool(my and my.role != "leader")
        ),
    }


def message_out(db: Session, msg) -> dict:
    sender = None
    if msg.sender_id is not None:
        user = db.get(User, msg.sender_id)
        sender = user_public(user)
    recalled = getattr(msg, "recalled_at", None) is not None
    return {
        "id": msg.id,
        "team_id": msg.team_id,
        "msg_type": msg.msg_type,
        # 撤回后不再下发原文，避免"撤回"变成摆设
        "content": "该消息已撤回" if recalled else msg.content,
        "recalled": recalled,
        "mentions_all": bool(getattr(msg, "mentions_all", False)),
        "sender": sender,
        "created_at": iso(msg.created_at),
    }


def checkin_out(db: Session, row: Checkin) -> dict:
    user = db.get(User, row.user_id)
    return {
        "user": user_public(user),
        "checked": row.checked_at is not None,
        "checked_at": iso(row.checked_at),
        # 核销码仅本人可见由服务层控制，这里不输出 code
    }


# 通知分类：todo=需要你处理（前端置顶 + 待办直达）；info=通知类
NOTIFICATION_CATEGORY = {
    "member_joined": "todo",
    "member_left": "info",
    "team_updated": "info",
    "kicked": "info",
    "formed": "info",
    "bill_submitted": "todo",
    "bill_effective": "todo",
    "team_failed": "info",
    "team_completed": "info",
    "checkin_reminder": "todo",
    "checkin_overdue": "todo",
    "checkin_escalated": "todo",
    "report_result": "info",
}


def notification_out(row) -> dict:
    try:
        payload = json.loads(row.payload)
    except Exception:
        payload = {}
    return {
        "id": row.id,
        "type": row.type,
        "team_id": row.team_id,
        "payload": payload,
        "category": NOTIFICATION_CATEGORY.get(row.type, "info"),
        "is_read": row.is_read,
        "created_at": iso(row.created_at),
    }
