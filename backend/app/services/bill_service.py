from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.engine import dispatch
from app.agent.events import TeamEvent
from app.agent.states import BillStatus, PaymentStatus
from app.core.audit import audit
from app.models.bill import Bill
from app.models.payment import Payment
from app.models.user import User
from app.schemas.serializers import iso, user_public
from app.services.common import dispatch_and_enqueue, enqueue, get_team_or_404


def _get_bill_or_404(db: Session, team_id: int) -> Bill:
    bill = db.execute(select(Bill).where(Bill.team_id == team_id)).scalar_one_or_none()
    if bill is None:
        raise HTTPException(status_code=404, detail="账单尚未创建，等待队长录入")
    return bill


def submit_bill(db: Session, team_id: int, actor: User, total_amount: Decimal) -> dict:
    team = get_team_or_404(db, team_id)
    dispatch_and_enqueue(db, team, TeamEvent.SUBMIT_BILL, actor, {"total_amount": total_amount})
    audit(db, actor.id, "bill.submit", "team", team_id, total_amount=str(total_amount))
    db.commit()
    bill = _get_bill_or_404(db, team_id)
    return {"team_id": team_id, "status": bill.status, "total_amount": float(bill.total_amount)}


def get_bill(db: Session, team_id: int, actor: User) -> dict:
    from app.services.common import assert_active_member

    team = get_team_or_404(db, team_id)
    assert_active_member(db, team_id, actor.id)
    bill = _get_bill_or_404(db, team_id)
    payments = db.execute(select(Payment).where(Payment.bill_id == bill.id)).scalars().all()
    items = []
    for p in payments:
        u = db.get(User, p.user_id)
        items.append(
            {
                "user": user_public(u),
                "amount": float(p.amount),
                "status": p.status,
                "is_me": p.user_id == actor.id,
                "paid_at": iso(p.paid_at),
            }
        )
    return {
        "team_id": team_id,
        "status": bill.status,
        "total_amount": float(bill.total_amount) if bill.total_amount is not None else None,
        "per_capita": float(bill.per_capita) if bill.per_capita is not None else None,
        "effective_at": iso(bill.effective_at),
        "payments": items,
        "paid_count": sum(1 for p in payments if p.status == PaymentStatus.PAID),
        "total_members": len(payments),
        # 按"实际到场者"分摊后，缺席者不会出现在 payments 里，前端据此给出说明
        "i_am_payer": any(p.user_id == actor.id for p in payments),
    }


def pay(db: Session, team_id: int, actor: User) -> dict:
    """本人独立结账（模拟支付，即时到账）。走状态机 PAY 事件保证原子与链式触发。"""
    team = get_team_or_404(db, team_id)
    dispatch_and_enqueue(db, team, TeamEvent.PAY, actor)
    db.commit()
    bill = _get_bill_or_404(db, team_id)
    return {"bill_id": bill.id, "status": bill.status, "paid": True}
