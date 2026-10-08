"""举报与拉黑接口。"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core import ratelimit
from app.core.config import settings
from app.core.deps import get_db, require_active, require_verified
from app.models.user import User
from app.schemas.requests import BlockIn, ReportIn
from app.services import report_service

router = APIRouter(prefix="/api", tags=["reports"])


@router.post("/reports")
def submit_report(data: ReportIn, user: User = Depends(require_verified),
                  db: Session = Depends(get_db)):
    # 防滥用举报
    ratelimit.check("report", user.id, settings.RATE_LIMIT_WRITE_PER_MIN)
    return report_service.submit_report(
        db, user, data.target_user_id, data.reason,
        team_id=data.team_id, message_id=data.message_id, detail=data.detail,
    )


@router.post("/blocks")
def block_user(data: BlockIn, user: User = Depends(require_verified),
               db: Session = Depends(get_db)):
    return report_service.block_user(db, user, data.target_user_id, data.reason)


@router.delete("/blocks/{target_user_id}")
def unblock_user(target_user_id: int, user: User = Depends(require_verified),
                 db: Session = Depends(get_db)):
    return report_service.unblock_user(db, user, target_user_id)
