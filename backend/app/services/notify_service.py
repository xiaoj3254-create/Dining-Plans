"""通知与巡检服务。

本次修复要点：
- 幂等改用结构化 `team_id` 列（原实现把 payload 当字符串做子串匹配，`team 5` 会被
  `team 55` 的历史通知误屏蔽，导致漏发提醒）；
- 核销超时改为**阶梯提醒**：T+2h 提醒队长 → T+12h 提醒全员 → T+24h 升级，
  不再"提醒一次就沉默"；
- 新增账单锁定的巡检收口（无人再核销时也必须能锁账）；
- 新增招募超时收口（转 team_service.expire_overdue）；
- 订阅消息待发队列的出队（provider 未接入时标记 skipped，不无限堆积）。
"""

import json
import logging
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agent import effects, guards
from app.agent.states import BillStatus, MemberStatus, TeamStatus
from app.core.config import settings
from app.core.timeutil import now
from app.models.bill import Bill
from app.models.checkin import Checkin
from app.models.member import TeamMember
from app.models.notification import Notification
from app.models.push import PushOutbox
from app.models.team import Team
from app.schemas.serializers import notification_out

logger = logging.getLogger("notify_service")


def list_notifications(db: Session, user_id: int, unread_only: bool, page: int = 1, page_size: int = 30) -> dict:
    conds = [Notification.user_id == user_id]
    if unread_only:
        conds.append(Notification.is_read.is_(False))
    total = db.execute(
        select(func.count()).select_from(Notification).where(*conds)
    ).scalar() or 0
    rows = db.execute(
        select(Notification).where(*conds)
        .order_by(Notification.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).scalars().all()
    unread = db.execute(
        select(func.count()).select_from(Notification).where(
            Notification.user_id == user_id, Notification.is_read.is_(False)
        )
    ).scalar() or 0
    return {
        "total": total,
        "unread": unread,
        "page": page,
        "page_size": page_size,
        "has_more": (page - 1) * page_size + len(rows) < total,
        "items": [notification_out(r) for r in rows],
    }


def mark_read(db: Session, user_id: int, notification_id: int) -> dict:
    row = db.get(Notification, notification_id)
    if row is None or row.user_id != user_id:
        raise HTTPException(status_code=404, detail="通知不存在")
    row.is_read = True
    db.commit()
    return {"id": row.id, "is_read": True}


def mark_all_read(db: Session, user_id: int) -> dict:
    rows = db.execute(
        select(Notification).where(Notification.user_id == user_id, Notification.is_read.is_(False))
    ).scalars().all()
    for r in rows:
        r.is_read = True
    db.commit()
    return {"updated": len(rows)}


def delete_notification(db: Session, user_id: int, notification_id: int) -> dict:
    """删除本人通知（左滑删除）。他人通知一律 404，不泄漏存在性"""
    row = db.get(Notification, notification_id)
    if row is None or row.user_id != user_id:
        raise HTTPException(status_code=404, detail="通知不存在")
    db.delete(row)
    db.commit()
    return {"id": notification_id, "deleted": True}


# ---------- 巡检辅助 ----------

def _sent(db: Session, user_id: int, ntype: str, team_id: int) -> bool:
    """幂等判定：某人某类型某队伍的通知是否已发过（走结构化列 + 索引）。"""
    row = db.execute(
        select(Notification.id).where(
            Notification.user_id == user_id,
            Notification.type == ntype,
            Notification.team_id == team_id,
        ).limit(1)
    ).first()
    return row is not None


def _active_members(db: Session, team_id: int) -> list[TeamMember]:
    return list(
        db.execute(
            select(TeamMember).where(
                TeamMember.team_id == team_id, TeamMember.status == MemberStatus.ACTIVE
            )
        ).scalars().all()
    )


def _notify(db: Session, user_id: int, ntype: str, team: Team, **payload) -> None:
    db.add(Notification(
        user_id=user_id, type=ntype, team_id=team.id,
        payload=json.dumps({"team_id": team.id, "team_name": team.name, **payload},
                           ensure_ascii=False),
    ))


def scan_checkin_timeout(db: Session, timeout_hours: int | None = None) -> dict:
    """到场确认超时的阶梯提醒。

    阶段 1（就餐 + CHECKIN_TIMEOUT_HOURS）：提醒队长
    阶段 2（就餐 + REMINDER_STAGE2_HOURS）：提醒全员
    阶段 3（就餐 + REMINDER_STAGE3_HOURS）：升级提醒（并提示可申请解散重开）
    """
    timeout_hours = timeout_hours if timeout_hours is not None else settings.CHECKIN_TIMEOUT_HOURS
    # 时间下限下推到 SQL：只拉"已到提醒时点"的队伍，避免每轮全量扫描全部 FORMED 队伍
    threshold = now() - timedelta(hours=timeout_hours)
    rows = db.execute(
        select(Team).where(
            Team.status == TeamStatus.FORMED.value,
            Team.dining_time.is_not(None),
            Team.dining_time < threshold,
        )
    ).scalars().all()

    current = now()
    result = {"stage1": 0, "stage2": 0, "stage3": 0}
    for team in rows:
        elapsed = current - team.dining_time
        if elapsed < timedelta(hours=timeout_hours):
            continue
        members = _active_members(db, team.id)
        if not members:
            continue
        ids = [m.user_id for m in members]
        unchecked = db.execute(
            select(func.count()).select_from(Checkin).where(
                Checkin.team_id == team.id,
                Checkin.user_id.in_(ids),
                Checkin.checked_at.is_(None),
            )
        ).scalar() or 0
        if not unchecked:
            continue

        # 阶段 1：提醒队长
        if not _sent(db, team.leader_id, effects.NOTIFY_CHECKIN_REMINDER, team.id):
            _notify(db, team.leader_id, effects.NOTIFY_CHECKIN_REMINDER, team,
                    unchecked=unchecked, stage=1)
            result["stage1"] += 1

        # 阶段 2：提醒全员
        if elapsed >= timedelta(hours=settings.REMINDER_STAGE2_HOURS):
            for m in members:
                if not _sent(db, m.user_id, effects.NOTIFY_CHECKIN_OVERDUE, team.id):
                    _notify(db, m.user_id, effects.NOTIFY_CHECKIN_OVERDUE, team,
                            unchecked=unchecked, stage=2)
                    result["stage2"] += 1

        # 阶段 3：升级（提示可协调解散重开）
        if elapsed >= timedelta(hours=settings.REMINDER_STAGE3_HOURS):
            for m in members:
                if not _sent(db, m.user_id, effects.NOTIFY_CHECKIN_ESCALATED, team.id):
                    _notify(db, m.user_id, effects.NOTIFY_CHECKIN_ESCALATED, team,
                            unchecked=unchecked, stage=3)
                    result["stage3"] += 1

    if any(result.values()):
        db.commit()
    return result


def scan_bill_lock(db: Session) -> int:
    """账单锁定收口：核销窗口已关闭且已录账单的队伍 → 触发 AUTO_BILL_LOCK。

    没有这个巡检，宽限期过后"无人再核销"的队伍将永远停留在 pending。
    """
    from app.agent.events import TeamEvent
    from app.services.common import dispatch_and_enqueue

    rows = db.execute(
        select(Team).join(Bill, Bill.team_id == Team.id).where(
            Team.status == TeamStatus.FORMED.value,
            Bill.status == BillStatus.PENDING,
            Bill.total_amount.is_not(None),
        )
    ).scalars().all()

    locked = 0
    for team in rows:
        if not guards.checkin_window_closed(db, team):
            continue
        try:
            dispatch_and_enqueue(db, team, TeamEvent.AUTO_BILL_LOCK, _system_actor())
            db.commit()
            locked += 1
        except HTTPException as e:
            db.rollback()
            logger.info("账单锁定巡检跳过 team=%s：%s", team.id, e.detail)
        except Exception:
            # 绝不静默：巡检静默失败等于业务永久卡死却无人知晓
            db.rollback()
            logger.exception("账单锁定巡检异常 team=%s", team.id)
    return locked


def _system_actor():
    from app.services.common import system_actor

    return system_actor()


def deliver_push_outbox(db: Session) -> dict:
    """订阅消息出队。

    `PUSH_PROVIDER == "none"`（未接正式 AppID）时把排队记录标记为 skipped，
    既保留完整的"该发什么"证据链，又不会让队列无限堆积。
    接入真实 provider 后在这里调用支付宝订阅消息 API 并写 sent/failed。
    """
    rows = db.execute(
        select(PushOutbox).where(PushOutbox.status == "pending").limit(200)
    ).scalars().all()
    if not rows:
        return {"processed": 0}

    if settings.PUSH_PROVIDER == "none":
        for r in rows:
            r.status = "skipped"
            r.error = "PUSH_PROVIDER=none（未接入订阅消息），站内通知已送达"
            r.sent_at = now()
    else:
        # provider 已配置但尚未实现：显式告警，防止误配后队列静默堆积
        logger.warning("PUSH_PROVIDER=%s 尚未实现，%s 条订阅消息保留 pending",
                       settings.PUSH_PROVIDER, len(rows))
        return {"processed": 0, "note": f"provider={settings.PUSH_PROVIDER} 尚未实现"}

    db.commit()
    return {"processed": len(rows), "status": "skipped"}


def run_all_scans(db: Session) -> dict:
    """巡检总入口（由后台循环调用）。"""
    from app.services.team_service import expire_overdue

    return {
        "checkin": scan_checkin_timeout(db),
        "bill_lock": scan_bill_lock(db),
        "recruiting_expired": expire_overdue(db),
        "push": deliver_push_outbox(db),
    }
