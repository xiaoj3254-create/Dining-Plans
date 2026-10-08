from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core import idempotency, ratelimit
from app.core.config import settings
from app.core.deps import get_db, require_active, require_verified
from app.models.user import User
from app.schemas.requests import BillIn
from app.services import bill_service

router = APIRouter(tags=["bills"])


@router.post("/api/teams/{team_id}/bill")
def submit_bill(team_id: int, data: BillIn, request: Request,
                user: User = Depends(require_active), db: Session = Depends(get_db)):
    ratelimit.check("write", user.id, settings.RATE_LIMIT_WRITE_PER_MIN)
    return idempotency.run_idempotent(
        db, user, request, "bill.submit",
        lambda: bill_service.submit_bill(db, team_id, user, data.total_amount),
    )


@router.get("/api/teams/{team_id}/bill")
def get_bill(team_id: int, user: User = Depends(require_verified), db: Session = Depends(get_db)):
    return bill_service.get_bill(db, team_id, user)


@router.post("/api/teams/{team_id}/bill/pay")
def pay(team_id: int, request: Request, user: User = Depends(require_active),
        db: Session = Depends(get_db)):
    """本人独立结账（模拟支付，即时到账）。

    带幂等键：401 自愈后用户手动重试时不会产生二次支付动作。
    """
    ratelimit.check("write", user.id, settings.RATE_LIMIT_WRITE_PER_MIN)
    return idempotency.run_idempotent(
        db, user, request, "bill.pay",
        lambda: bill_service.pay(db, team_id, user),
    )
