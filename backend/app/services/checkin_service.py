from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.events import TeamEvent
from app.models.checkin import Checkin
from app.models.user import User
from app.schemas.serializers import checkin_out, user_public
from app.services.common import assert_active_member, dispatch_and_enqueue, get_team_or_404


def checkin(db: Session, team_id: int, actor: User, code: str) -> dict:
    team = get_team_or_404(db, team_id)
    dispatch_and_enqueue(db, team, TeamEvent.CHECKIN, actor, {"checkin_code": code})
    db.commit()
    return {"team_id": team_id, "checked": True}


def list_checkins(db: Session, team_id: int, actor: User) -> dict:
    """全员到场进度。★ 必须校验成员身份：
    原实现只做 get_team_or_404，导致任何实名用户都能读到已成团队伍的完整名单
    （绕过了详情接口对非成员的 403 控制）。"""
    team = get_team_or_404(db, team_id)
    assert_active_member(db, team_id, actor.id)
    from app.agent import guards

    active_ids = guards.active_member_ids(db, team)
    rows = db.execute(
        select(Checkin).where(Checkin.team_id == team_id, Checkin.user_id.in_(active_ids))
    ).scalars().all() if active_ids else []
    if not rows:
        raise HTTPException(status_code=404, detail="队伍尚未成团，暂无到场记录")
    checked = sum(1 for r in rows if r.checked_at is not None)
    return {
        "team_id": team_id,
        "checked": checked,
        "total": len(rows),
        "all_checked": checked == len(rows),
        "items": [checkin_out(db, r) for r in rows],
    }


def my_checkin_code(db: Session, team_id: int, actor: User) -> dict:
    """本人核销码（仅自己可见；非成员一律 403）"""
    get_team_or_404(db, team_id)
    assert_active_member(db, team_id, actor.id)
    row = db.execute(
        select(Checkin).where(Checkin.team_id == team_id, Checkin.user_id == actor.id)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="核销记录不存在")
    return {"team_id": team_id, "checkin_code": row.checkin_code, "checked": row.checked_at is not None}
