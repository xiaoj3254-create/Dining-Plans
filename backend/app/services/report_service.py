"""举报与拉黑服务。

审计发现：陌生人线下社交却没有任何举报/拉黑通道——这是风险最高的一段缺口。
本模块提供：
- 举报落工单（reports 表）+ 累计计数；
- 达到阈值自动限制账号（可用 settings.REPORT_AUTO_RESTRICT_THRESHOLD 关闭）；
- 举报人可选择同时拉黑（user_blocks，跨队生效）。
"""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent import effects
from app.core.audit import audit
from app.core.config import settings
from app.core.timeutil import now
from app.models.block import UserBlock
from app.models.member import TeamMember
from app.models.message import Message
from app.models.report import Report
from app.models.team import Team
from app.models.user import User

VALID_REASONS = {"harassment", "fraud", "abuse", "illegal", "other"}


def submit_report(db: Session, reporter: User, target_user_id: int, reason: str,
                  team_id: int | None = None, message_id: int | None = None,
                  detail: str | None = None) -> dict:
    if reason not in VALID_REASONS:
        raise HTTPException(status_code=422, detail="举报原因不合法")
    if target_user_id == reporter.id:
        raise HTTPException(status_code=400, detail="不能举报自己")

    target = db.get(User, target_user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="被举报用户不存在")

    # 举证上下文校验：不允许拿别人的队伍/消息做举报素材
    if team_id is not None:
        team = db.get(Team, team_id)
        if team is None:
            raise HTTPException(status_code=404, detail="队伍不存在")
        mine = db.execute(
            select(TeamMember.id).where(
                TeamMember.team_id == team_id, TeamMember.user_id == reporter.id
            ).limit(1)
        ).first()
        if mine is None:
            raise HTTPException(status_code=403, detail="你不在该队伍中，无法以此为证据举报")
    if message_id is not None:
        msg = db.get(Message, message_id)
        if msg is None:
            raise HTTPException(status_code=404, detail="消息不存在")

    report = Report(
        reporter_id=reporter.id, target_user_id=target_user_id, team_id=team_id,
        message_id=message_id, reason=reason, detail=(detail or None),
    )
    db.add(report)

    target.report_count = (target.report_count or 0) + 1
    threshold = settings.REPORT_AUTO_RESTRICT_THRESHOLD
    restricted_now = False
    if threshold > 0 and target.report_count >= threshold and target.restricted_at is None:
        target.restricted_at = now()
        target.restricted_reason = f"被举报累计 {target.report_count} 次待人工复核"
        restricted_now = True

    audit(db, reporter.id, "user.report", "user", target_user_id,
          reason=reason, team_id=team_id, message_id=message_id)
    db.commit()

    return {
        "report_id": report.id,
        "status": "received",
        "target_restricted": restricted_now,
        "message": "举报已受理，我们会尽快核查。你也可以在队伍详情中拉黑该用户。",
    }


def block_user(db: Session, blocker: User, target_user_id: int, reason: str | None = None) -> dict:
    """拉黑：跨队生效——对方无法加入我的队伍，我也看不到对方的队伍。"""
    if target_user_id == blocker.id:
        raise HTTPException(status_code=400, detail="不能拉黑自己")
    if db.get(User, target_user_id) is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    exists = db.execute(
        select(UserBlock).where(
            UserBlock.blocker_id == blocker.id, UserBlock.blocked_id == target_user_id
        )
    ).scalar_one_or_none()
    if exists is None:
        db.add(UserBlock(blocker_id=blocker.id, blocked_id=target_user_id,
                         reason=(reason or "用户主动拉黑")[:100]))
        audit(db, blocker.id, "user.block", "user", target_user_id, reason=reason)
        db.commit()
    return {"blocked": True, "target_user_id": target_user_id}


def unblock_user(db: Session, blocker: User, target_user_id: int) -> dict:
    row = db.execute(
        select(UserBlock).where(
            UserBlock.blocker_id == blocker.id, UserBlock.blocked_id == target_user_id
        )
    ).scalar_one_or_none()
    if row is not None:
        db.delete(row)
        db.commit()
    return {"blocked": False, "target_user_id": target_user_id}


def blocked_ids(db: Session, user_id: int) -> list[int]:
    """我拉黑的 + 拉黑我的（用于广场过滤）。"""
    rows = db.execute(
        select(UserBlock.blocker_id, UserBlock.blocked_id).where(
            (UserBlock.blocker_id == user_id) | (UserBlock.blocked_id == user_id)
        )
    ).all()
    ids: set[int] = set()
    for blocker, blocked in rows:
        ids.add(blocked if blocker == user_id else blocker)
    ids.discard(user_id)
    return sorted(ids)
