from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core import idempotency, ratelimit
from app.core.config import settings
from app.core.deps import get_db, require_active, require_verified
from app.models.user import User
from app.schemas.requests import TeamCreateIn, TeamUpdateIn
from app.services import team_service

router = APIRouter(prefix="/api/teams", tags=["teams"])


@router.post("")
def create_team(data: TeamCreateIn, user: User = Depends(require_verified), db: Session = Depends(get_db)):
    return team_service.create_team(db, user, data)


@router.post("/join/{code}")
def join_by_link(code: str, request: Request, user: User = Depends(require_active),
                 db: Session = Depends(get_db)):
    """链接报名（模式二）。注意：必须注册在 /{team_id} 之前，避免路径参数吞掉 join"""
    # 邀请码遍历防护（配合 12 位邀请码）
    ratelimit.check("invite_try", user.id, settings.RATE_LIMIT_INVITE_TRY_PER_MIN)
    return idempotency.run_idempotent(
        db, user, request, "teams.join_by_link",
        lambda: team_service.join_by_link(db, code, user),
    )


@router.patch("/{team_id}")
def update_draft(team_id: int, data: TeamUpdateIn, user: User = Depends(require_verified),
                 db: Session = Depends(get_db)):
    return team_service.update_draft(db, team_id, user, data.model_dump(exclude_unset=True))


@router.post("/{team_id}/publish")
def publish(team_id: int, user: User = Depends(require_active), db: Session = Depends(get_db)):
    return team_service.publish(db, team_id, user)


@router.get("/{team_id}")
def get_detail(team_id: int, user: User = Depends(require_verified), db: Session = Depends(get_db)):
    return team_service.get_detail(db, team_id, user)


@router.post("/{team_id}/join")
def join(team_id: int, request: Request, user: User = Depends(require_active),
         db: Session = Depends(get_db)):
    return idempotency.run_idempotent(
        db, user, request, "teams.join",
        lambda: team_service.join(db, team_id, user),
    )


@router.post("/{team_id}/leave")
def leave(team_id: int, request: Request, user: User = Depends(require_verified),
          db: Session = Depends(get_db)):
    return idempotency.run_idempotent(
        db, user, request, "teams.leave",
        lambda: team_service.leave(db, team_id, user),
    )


@router.post("/{team_id}/members")
def fill_seat(team_id: int, target_user_id: int, user: User = Depends(require_active),
              db: Session = Depends(get_db)):
    """队长补招：成团后账单生效前，把空缺席位补给指定用户"""
    return team_service.fill_seat(db, team_id, target_user_id, user)


@router.post("/{team_id}/members/{user_id}/kick")
def kick(team_id: int, user_id: int, request: Request, user: User = Depends(require_active),
         db: Session = Depends(get_db)):
    return idempotency.run_idempotent(
        db, user, request, "teams.kick",
        lambda: team_service.kick(db, team_id, user_id, user),
    )


@router.post("/{team_id}/disband")
def disband(team_id: int, user: User = Depends(require_active), db: Session = Depends(get_db)):
    return team_service.disband(db, team_id, user)


@router.post("/{team_id}/invite/close")
def close_invite(team_id: int, user: User = Depends(require_active), db: Session = Depends(get_db)):
    return team_service.close_invite(db, team_id, user)


@router.post("/{team_id}/abort")
def abort(team_id: int, user: User = Depends(require_active), db: Session = Depends(get_db)):
    return team_service.abort(db, team_id, user)


@router.post("/{team_id}/recreate")
def recreate(team_id: int, request: Request, user: User = Depends(require_active),
             db: Session = Depends(get_db)):
    return idempotency.run_idempotent(
        db, user, request, "teams.recreate",
        lambda: team_service.recreate(db, team_id, user),
    )
