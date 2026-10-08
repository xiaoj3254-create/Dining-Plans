"""组队服务。

本次修复要点：
- 删除 `datetime.max` 哨兵：草稿期字段就是 NULL，由发布守卫强校验（原实现可发布无时间的饭局）；
- 菜品失效不再让整表保存失败，改为"剔除 + 回报被剔除项"；
- 成团后允许队员在账单生效前退出，队长可在同一窗口补招（把"只能解散重开"换成可运营的闭环）；
- 敏感操作落审计日志。
"""

import json
import logging

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.events import TeamEvent
from app.agent.states import MemberRole, TeamStatus
from app.core.audit import audit
from app.core.timeutil import now
from app.models.dish import Dish
from app.models.member import TeamMember
from app.models.restaurant import Restaurant
from app.models.team import Team
from app.models.user import User
from app.schemas.serializers import food_image, team_detail
from app.services.common import (
    active_member,
    assert_leader,
    assert_not_restricted,
    dispatch_and_enqueue,
    get_team_or_404,
)

logger = logging.getLogger("team_service")


def _get_restaurant_or_422(db: Session, restaurant_id: int) -> Restaurant:
    r = db.get(Restaurant, restaurant_id)
    if r is None or not r.is_active:
        raise HTTPException(status_code=422, detail="餐馆不存在或已下架")
    return r


def _build_menu_items(db: Session, dish_ids, restaurant_id: int | None = None) -> tuple[str | None, list[str]]:
    """按菜品 id 重建预选菜单快照（服务端定价，忽略前端传来的价格）。

    返回 (菜单 JSON, 被剔除的菜品说明)。区分两种"坏 id"：
    - **完全不存在 / 不属于所选餐馆**：属前端脏数据或构造请求 → 422 直接暴露；
    - **存在但已下架**：属业务变化 → 剔除并回报，不让"改个队伍名"因为一道菜下架而整表失败。
    """
    if not dish_ids:
        return None, []
    ids = list(dict.fromkeys(int(i) for i in dish_ids))  # 去重且保序
    rows = db.execute(select(Dish).where(Dish.id.in_(ids))).scalars().all()
    by_id = {d.id: d for d in rows}

    unknown = [i for i in ids if i not in by_id]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail="菜品不存在：" + "、".join(str(i) for i in unknown),
        )
    if restaurant_id is not None:
        foreign = [i for i in ids if by_id[i].restaurant_id != restaurant_id]
        if foreign:
            raise HTTPException(
                status_code=422,
                detail="所选菜品不属于该餐馆：" + "、".join(str(i) for i in foreign),
            )

    items, removed = [], []
    for i in ids:
        d = by_id[i]
        if not d.is_active:
            removed.append(d.name)
            continue
        items.append({
            "dish_id": d.id,
            "name": d.name,
            "price": float(d.price),
            "image": food_image(d.image),
        })
    return json.dumps(items, ensure_ascii=False), removed


def create_team(db: Session, actor: User, data) -> dict:
    assert_not_restricted(actor)
    if data.restaurant_id is not None:
        _get_restaurant_or_422(db, data.restaurant_id)
    menu_items, removed = _build_menu_items(db, data.dish_ids, data.restaurant_id)
    team = Team(
        name=data.name,
        mode=data.mode,
        # 草稿期允许缺省（NULL）：发布时由 g_publish_fields 强校验，不再用哨兵值占位
        target_size=data.target_size,
        cuisine_type=data.cuisine_type,
        menu_summary=data.menu_summary,
        menu_items=menu_items,
        dining_time=data.dining_time,
        location_hint=data.location_hint,
        restaurant_id=data.restaurant_id,
        leader_id=actor.id,
        status=TeamStatus.DRAFT.value,
        current_size=1,
    )
    db.add(team)
    db.flush()
    db.add(TeamMember(team_id=team.id, user_id=actor.id, role=MemberRole.LEADER))
    audit(db, actor.id, "team.create", "team", team.id, mode=team.mode)
    db.commit()
    out = {"id": team.id, "status": team.status}
    if removed:
        out["removed_dishes"] = removed
    return out


def update_draft(db: Session, team_id: int, actor: User, data: dict) -> dict:
    team = get_team_or_404(db, team_id)
    payload = dict(data)
    removed: list[str] = []
    dish_ids = payload.pop("dish_ids", None)
    if dish_ids is not None:
        payload["menu_items"], removed = _build_menu_items(
            db, dish_ids, payload.get("restaurant_id") or team.restaurant_id
        )
    rid = payload.get("restaurant_id")
    if rid is not None:
        _get_restaurant_or_422(db, rid)
        if dish_ids is None and rid != team.restaurant_id:
            payload["menu_items"] = "[]"  # 换店且未带菜品：清空旧店快照
    dispatch_and_enqueue(db, team, TeamEvent.UPDATE_DRAFT, actor, payload)
    db.commit()
    out = {"id": team.id, "status": team.status}
    if removed:
        out["removed_dishes"] = removed
    return out


def publish(db: Session, team_id: int, actor: User) -> dict:
    team = get_team_or_404(db, team_id)
    assert_not_restricted(actor)
    dispatch_and_enqueue(db, team, TeamEvent.PUBLISH, actor)
    audit(db, actor.id, "team.publish", "team", team.id, mode=team.mode)
    db.commit()
    db.refresh(team)
    return {"id": team.id, "status": team.status, "code": team.code}


def get_detail(db: Session, team_id: int, viewer: User) -> dict:
    team = get_team_or_404(db, team_id)
    if team.status != TeamStatus.RECRUITING.value and active_member(db, team.id, viewer.id) is None:
        # 非成员仅可查看招募中的队伍概况；成团/完结队伍信息仅成员可见
        raise HTTPException(status_code=403, detail="该队伍已关闭报名，仅成员可查看")
    return team_detail(db, team, viewer.id)


def join(db: Session, team_id: int, actor: User) -> dict:
    assert_not_restricted(actor)
    team = get_team_or_404(db, team_id)
    dispatch_and_enqueue(db, team, TeamEvent.JOIN, actor)
    db.commit()
    db.refresh(team)
    return {"id": team.id, "status": team.status, "current_size": team.current_size}


def join_by_link(db: Session, code: str, actor: User) -> dict:
    assert_not_restricted(actor)
    team = db.execute(select(Team).where(Team.code == code)).scalar_one_or_none()
    if team is None:
        raise HTTPException(status_code=404, detail="邀请码无效")
    dispatch_and_enqueue(db, team, TeamEvent.JOIN_BY_LINK, actor, {"code": code})
    db.commit()
    db.refresh(team)
    return {"id": team.id, "status": team.status, "current_size": team.current_size}


def leave(db: Session, team_id: int, actor: User) -> dict:
    team = get_team_or_404(db, team_id)
    dispatch_and_enqueue(db, team, TeamEvent.LEAVE, actor)
    audit(db, actor.id, "team.leave", "team", team_id)
    db.commit()
    db.refresh(team)
    return {"id": team.id, "status": team.status, "current_size": team.current_size}


def kick(db: Session, team_id: int, target_user_id: int, actor: User) -> dict:
    team = get_team_or_404(db, team_id)
    dispatch_and_enqueue(db, team, TeamEvent.KICK, actor, {"target_user_id": target_user_id})
    audit(db, actor.id, "team.kick", "team", team_id, target_user_id=target_user_id)
    db.commit()
    db.refresh(team)
    return {"id": team.id, "current_size": team.current_size}


def fill_seat(db: Session, team_id: int, target_user_id: int, actor: User) -> dict:
    """队长补招：成团后账单生效前，把空缺名额补给指定用户（替代"只能解散重开"）。

    被补招者此前必须与该队无成员关系（被踢过 / 已在队内都会被守卫拦下）。
    """
    team = get_team_or_404(db, team_id)
    target = db.get(User, target_user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="目标用户不存在")
    if not target.real_name_verified:
        raise HTTPException(status_code=422, detail="该用户尚未完成实名认证")
    dispatch_and_enqueue(db, team, TeamEvent.FILL_SEAT, actor, {"target_user_id": target_user_id})
    audit(db, actor.id, "team.fill_seat", "team", team_id, target_user_id=target_user_id)
    db.commit()
    db.refresh(team)
    return {"id": team.id, "current_size": team.current_size}


def disband(db: Session, team_id: int, actor: User) -> dict:
    team = get_team_or_404(db, team_id)
    dispatch_and_enqueue(db, team, TeamEvent.DISBAND, actor)
    audit(db, actor.id, "team.disband", "team", team_id)
    db.commit()
    return {"id": team.id, "status": team.status, "fail_reason": team.fail_reason}


def close_invite(db: Session, team_id: int, actor: User) -> dict:
    team = get_team_or_404(db, team_id)
    dispatch_and_enqueue(db, team, TeamEvent.CLOSE_INVITE, actor)
    db.commit()
    return {"id": team.id, "invite_open": team.invite_open}


def abort(db: Session, team_id: int, actor: User) -> dict:
    team = get_team_or_404(db, team_id)
    dispatch_and_enqueue(db, team, TeamEvent.ABORT, actor)
    audit(db, actor.id, "team.abort", "team", team_id)
    db.commit()
    return {"id": team.id, "status": team.status, "fail_reason": team.fail_reason}


def recreate(db: Session, team_id: int, actor: User) -> dict:
    """复制原配置新建草稿（核销异常解散 / 招募超时后重开）。

    注意：过期就餐时间不再用哨兵值兜底，而是置为 NULL，由用户在草稿里重新选择
    （原实现会填入 datetime.max，导致"必填校验"被绕过）。
    """
    team = get_team_or_404(db, team_id)
    assert_leader(db, team, actor)
    if team.status not in (TeamStatus.FAILED.value,):
        raise HTTPException(status_code=409, detail="仅异常终止的队伍可复制重开")
    new_team = Team(
        name=f"{team.name}（重开）"[:50],
        mode=team.mode,
        target_size=team.target_size,
        cuisine_type=team.cuisine_type,
        menu_summary=team.menu_summary,
        menu_items=team.menu_items,
        dining_time=team.dining_time if (team.dining_time and team.dining_time > now()) else None,
        location_hint=team.location_hint,
        restaurant_id=team.restaurant_id,  # 必须复制，否则重开的草稿发布时缺餐馆
        leader_id=actor.id,
        status=TeamStatus.DRAFT.value,
        current_size=1,
    )
    db.add(new_team)
    db.flush()
    db.add(TeamMember(team_id=new_team.id, user_id=actor.id, role=MemberRole.LEADER))
    audit(db, actor.id, "team.recreate", "team", new_team.id, from_team=team_id)
    db.commit()
    return {"id": new_team.id, "status": new_team.status}


def expire_overdue(db: Session) -> int:
    """招募超时巡检：就餐时间 + 宽限期仍未满员 → failed(expired) 并下架广场。

    原实现的过期队伍会永久停留在 recruiting，持续占用广场并让报名者无限等待。
    """
    from datetime import timedelta

    from app.core.config import settings

    if settings.RECRUITING_EXPIRE_GRACE_HOURS <= 0:
        return 0

    deadline = now() - timedelta(hours=settings.RECRUITING_EXPIRE_GRACE_HOURS)
    rows = db.execute(
        select(Team).where(
            Team.status == TeamStatus.RECRUITING.value,
            Team.dining_time.is_not(None),
            Team.dining_time < deadline,
        )
    ).scalars().all()

    done = 0
    for team in rows:
        try:
            dispatch_and_enqueue(db, team, TeamEvent.EXPIRE, system_actor())
            db.commit()
            done += 1
        except HTTPException as e:
            db.rollback()
            logger.info("招募超时巡检跳过 team=%s：%s", team.id, e.detail)
        except Exception:
            db.rollback()
            logger.exception("招募超时巡检异常 team=%s", team.id)
    return done


def system_actor() -> User:
    """系统巡检用的虚拟 actor（见 services.common.SystemActor 的说明）。"""
    from app.services.common import system_actor as _actor

    return _actor()
