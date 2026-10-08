from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core import idempotency
from app.core.deps import get_db, require_active, require_verified
from app.models.user import User
from app.schemas.requests import CheckinIn
from app.services import checkin_service

router = APIRouter(prefix="/api/teams", tags=["checkin"])


@router.post("/{team_id}/checkin")
def checkin(team_id: int, data: CheckinIn, request: Request,
            user: User = Depends(require_active), db: Session = Depends(get_db)):
    """到场确认（MVP 语义：本人确认到场，非商家扫码；见 README 与账单页文案）"""
    return idempotency.run_idempotent(
        db, user, request, "checkin.confirm",
        lambda: checkin_service.checkin(db, team_id, user, data.checkin_code),
    )


@router.get("/{team_id}/checkins")
def list_checkins(team_id: int, user: User = Depends(require_verified), db: Session = Depends(get_db)):
    return checkin_service.list_checkins(db, team_id, user)


@router.get("/{team_id}/checkins/me")
def my_checkin(team_id: int, user: User = Depends(require_verified), db: Session = Depends(get_db)):
    return checkin_service.my_checkin_code(db, team_id, user)
