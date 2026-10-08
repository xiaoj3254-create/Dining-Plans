"""状态机副作用。签名统一：(db, team, actor, payload, chain) -> list[dict]。

返回值是待入队 task_queue 的任务列表（WS 广播类）。
chain(event) 用于同事务内链式触发后续事件（满员成团 / 核销截止锁定账单 / 全付清完成）。

本次修复要点：
- 时间统一走 `timeutil.now()`（时区可控）；
- 成员进出写 `team_member_events` 流水（真正的历史留痕）；
- 招募期关键事件落站内通知（队长离线也能看到"有人报名了"）；
- 分账以"实际到场人数"为口径，缺席者不参与；
- 高时效事件同时写入 `push_outbox`（订阅消息接入点）。
"""

import secrets
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent import guards
from app.agent.concurrency import decrement_size
from app.agent.engine import GuardRejected
from app.agent.events import TeamEvent
from app.agent.states import (
    BillStatus,
    FailReason,
    MemberRole,
    MemberStatus,
    PaymentStatus,
    TeamMode,
    TeamStatus,
)
from app.core.timeutil import now
from app.models.bill import Bill
from app.models.checkin import Checkin
from app.models.member import TeamMember
from app.models.member_event import TeamMemberEvent
from app.models.message import Message
from app.models.notification import Notification
from app.models.payment import Payment
from app.models.push import PushOutbox
from app.models.user import User
from app.schemas.serializers import user_public  # noqa: F401 (脱敏出口统一在 serializers)

NOTIFY_MEMBER_JOINED = "member_joined"
NOTIFY_MEMBER_LEFT = "member_left"
NOTIFY_TEAM_UPDATED = "team_updated"
NOTIFY_BILL_SUBMITTED = "bill_submitted"
NOTIFY_KICKED = "kicked"
NOTIFY_FORMED = "formed"
NOTIFY_BILL_EFFECTIVE = "bill_effective"
NOTIFY_TEAM_FAILED = "team_failed"
NOTIFY_TEAM_COMPLETED = "team_completed"
NOTIFY_CHECKIN_REMINDER = "checkin_reminder"
NOTIFY_CHECKIN_OVERDUE = "checkin_overdue"
NOTIFY_CHECKIN_ESCALATED = "checkin_escalated"
NOTIFY_REPORT_RESULT = "report_result"

# 需要触达"小程序订阅消息"的场景（站内红点只能在用户主动进入小程序时被看到）
PUSH_SCENES = (NOTIFY_FORMED, NOTIFY_BILL_EFFECTIVE, NOTIFY_CHECKIN_REMINDER)

MEMBER_EVENT_JOINED = "joined"
MEMBER_EVENT_REJOINED = "rejoined"
MEMBER_EVENT_LEFT = "left"
MEMBER_EVENT_KICKED = "kicked"


# ---------- 内部工具 ----------

def _task(channel: str, event: str, data: dict) -> dict:
    return {"kind": "broadcast", "payload": {"channel": channel, "event": event, "data": data}}


def _kick_task(team, user_id: int) -> dict:
    """踢出/退出队伍后，让 worker 把该用户的 WS 连接从队伍频道摘除。

    频道订阅只在订阅时刻校验成员身份，不主动断订的话被踢成员的存活连接
    仍会收到该队事件（泄漏窗口）。注意与 e_* 副作用同事务入队，断订由
    worker 异步执行——提交与摘除之间至多一个轮询周期（毫秒级）的窗口。
    """
    return {"kind": "kick_channel", "payload": {"channel": _team_channel(team), "user_id": user_id}}


def _team_channel(team) -> str:
    return f"team:{team.id}"


def payload_json(payload: dict) -> str:
    import json
    return json.dumps(payload, ensure_ascii=False)


def _push(db: Session, user_id: int, scene: str, data: dict) -> None:
    """把高时效通知投入订阅消息待发队列。

    真实推送依赖正式 AppID 与模板 ID（settings.PUSH_PROVIDER），在拿到凭据前
    以"落库排队"的方式固化意图：业务代码不必在接入时再改一遍。
    """
    if scene not in PUSH_SCENES:
        return
    db.add(PushOutbox(user_id=user_id, scene=scene, template_data=payload_json(data)))


def _notify(db: Session, user_id: int, ntype: str, payload: dict,
            team_id: int | None = None) -> dict:
    """落一条站内通知（结构化 team_id），并返回其个人频道的广播任务"""
    db.add(Notification(
        user_id=user_id, type=ntype, team_id=team_id, payload=payload_json(payload),
    ))
    _push(db, user_id, ntype, payload)
    return _task(f"user:{user_id}", "notification.new",
                 {"type": ntype, "team_id": team_id, **payload})


def _record_event(db: Session, team, user_id: int, action: str,
                  operator_id: int | None = None, note: str | None = None) -> None:
    """写成员进出流水（历史留痕：TeamMember 一行只表达当前状态）。"""
    db.add(TeamMemberEvent(
        team_id=team.id, user_id=user_id, action=action,
        operator_id=operator_id, note=note,
    ))


def _active_members(db: Session, team) -> list[TeamMember]:
    return (
        db.execute(
            select(TeamMember).where(
                TeamMember.team_id == team.id, TeamMember.status == MemberStatus.ACTIVE
            )
        )
        .scalars()
        .all()
    )


def _get_bill(db: Session, team) -> Bill | None:
    return db.execute(select(Bill).where(Bill.team_id == team.id)).scalar_one_or_none()


def _gen_invite_code(db: Session) -> str:
    from app.models.team import Team

    while True:
        code = secrets.token_hex(6)  # 12 位（原 8 位十六进制可被暴力遍历）
        if db.execute(select(Team.id).where(Team.code == code)).first() is None:
            return code


def _status_tasks(team) -> list[dict]:
    return [_task(_team_channel(team), "team.status_changed",
                  {"team_id": team.id, "to": team.status})]


# ---------- 各事件副作用 ----------

def e_update_draft(db, team, actor, payload, chain) -> list[dict]:
    data = payload or {}
    fields = ["name", "mode", "target_size", "cuisine_type", "menu_summary",
              "menu_items", "dining_time", "location_hint", "restaurant_id"]
    for f in fields:
        if f in data and data[f] is not None:
            setattr(team, f, data[f])
    return []


def e_publish(db, team, actor, payload, chain) -> list[dict]:
    if team.mode == TeamMode.INVITE:
        team.code = _gen_invite_code(db)
    return [_task("plaza", "plaza.changed", {"team_id": team.id, "kind": "new"})]


def e_update_published(db, team, actor, payload, chain) -> list[dict]:
    """招募期修改饭局：更新字段 + 通知全部队员 + 广播。

    与草稿期 e_update_draft 的区别在于"有人已经在队里了"，所以必须把变更同步出去——
    否则队员看到的还是旧时间/旧餐馆，到了现场才发现改了。
    """
    tasks = e_update_draft(db, team, actor, payload, chain)
    changed = [k for k, v in (payload or {}).items() if k not in ("dish_ids",)]
    for m in _active_members(db, team):
        if m.user_id == actor.id:
            continue
        tasks.append(_notify(
            db, m.user_id, NOTIFY_TEAM_UPDATED,
            {"team_id": team.id, "team_name": team.name,
             "changed_fields": changed,
             "dining_time": team.dining_time.strftime("%Y-%m-%d %H:%M") if team.dining_time else None,
             "restaurant_changed": "restaurant_id" in (payload or {}),
             "menu_changed": "menu_items" in (payload or {})},
            team_id=team.id,
        ))
    tasks.append(_task(_team_channel(team), "team.updated",
                       {"team_id": team.id, "changed_fields": changed}))
    tasks.append(_task("plaza", "plaza.changed", {"team_id": team.id, "kind": "refresh"}))
    # 队长把人数改小到刚好满员时，应当立即成团——否则会出现
    # "剩余名额 0 却仍挂在招募中"的僵尸状态
    if team.target_size and team.current_size >= team.target_size:
        try:
            tasks += chain(TeamEvent.AUTO_FORM)
        except GuardRejected:
            pass
    return tasks


def e_member_joined(db, team, actor, payload, chain) -> list[dict]:
    db.refresh(team)  # 同步原子 UPDATE 后的最新人数
    member = db.execute(
        select(TeamMember).where(TeamMember.team_id == team.id, TeamMember.user_id == actor.id)
    ).scalar_one_or_none()
    if member is not None:  # 复活式重加入
        member.status = MemberStatus.ACTIVE
        member.left_at = None
        member.joined_at = now()
        _record_event(db, team, actor.id, MEMBER_EVENT_REJOINED, operator_id=actor.id)
    else:
        db.add(TeamMember(team_id=team.id, user_id=actor.id, role=MemberRole.MEMBER))
        _record_event(db, team, actor.id, MEMBER_EVENT_JOINED, operator_id=actor.id)

    remaining = (team.target_size - team.current_size) if team.target_size else None
    tasks = [
        _task(
            _team_channel(team),
            "team.member_joined",
            {"team_id": team.id, "member": user_public(actor), "current_size": team.current_size,
             "target_size": team.target_size, "remaining": remaining},
        ),
        _task("plaza", "plaza.changed", {"team_id": team.id, "kind": "refresh"}),
    ]
    # 招募期关键事件必须落站内通知：队长不在线时 WS 事件会永久丢失
    if team.leader_id != actor.id:
        tasks.append(_notify(
            db, team.leader_id, NOTIFY_MEMBER_JOINED,
            {"team_id": team.id, "team_name": team.name,
             "member_nickname": actor.nickname,
             "current_size": team.current_size, "target_size": team.target_size},
            team_id=team.id,
        ))
    if team.target_size and team.current_size >= team.target_size:
        # 仅在招募态链式成团；(formed, join) 不在流转表内，此判断纯属防御
        if team.status == TeamStatus.RECRUITING.value:
            try:
                tasks += chain(TeamEvent.AUTO_FORM)
            except GuardRejected:
                pass  # 链式成团守卫失败不应阻断报名本身；其余异常照常抛出
    return tasks


def e_fill_seat(db, team, actor, payload, chain) -> list[dict]:
    """补招：新增成员行 + 立刻生成其到场确认码 + 通知本人与队伍。

    两种入口共用本副作用：
    - 队长指定补招（payload.target_user_id）；
    - 邀请码补位（无 target_user_id，即 actor 本人持码进来）。

    守卫允许曾 LEFT 的用户补位，因此这里必须处理"复活"：TeamMember 一人一行
    （uq_member_team_user），无条件 db.add 会撞唯一约束变成莫名的 409；
    成团期退队者已有 Checkin 行，同样要先查再改。
    """
    target_id = int((payload or {}).get("target_user_id") or actor.id)
    db.refresh(team)
    member = db.execute(
        select(TeamMember).where(TeamMember.team_id == team.id, TeamMember.user_id == target_id)
    ).scalar_one_or_none()
    if member is not None:  # 曾退队（守卫已排除 active/kicked）：复活旧行
        member.status = MemberStatus.ACTIVE
        member.role = MemberRole.MEMBER
        member.left_at = None
        member.joined_at = now()
        action = MEMBER_EVENT_REJOINED
    else:
        db.add(TeamMember(team_id=team.id, user_id=target_id, role=MemberRole.MEMBER))
        action = MEMBER_EVENT_JOINED
    checkin = db.execute(
        select(Checkin).where(Checkin.team_id == team.id, Checkin.user_id == target_id)
    ).scalar_one_or_none()
    if checkin is not None:  # 成团期退队者的旧核销记录：换新码并要求重新确认到场
        checkin.checkin_code = secrets.token_hex(8)
        checkin.checked_at = None
    else:
        db.add(Checkin(team_id=team.id, user_id=target_id, checkin_code=secrets.token_hex(8)))
    _record_event(db, team, target_id, action, operator_id=actor.id, note="补招入队")
    db.add(Message(
        team_id=team.id, sender_id=None, msg_type="system",
        content="一位新成员补位入队，请留意群内沟通与到店安排。",
    ))
    target = db.get(User, target_id)
    tasks = [
        _task(_team_channel(team), "team.member_joined",
              {"team_id": team.id, "member": user_public(target),
               "current_size": team.current_size, "target_size": team.target_size,
               "remaining": (team.target_size - team.current_size) if team.target_size else None}),
    ]
    tasks.append(_notify(db, target_id, NOTIFY_FORMED,
                         {"team_id": team.id, "team_name": team.name,
                          "joined_as_replacement": True},
                         team_id=team.id))
    return tasks


def e_member_left(db, team, actor, payload, chain) -> list[dict]:
    member = db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team.id, TeamMember.user_id == actor.id,
            TeamMember.status == MemberStatus.ACTIVE,
        )
    ).scalar_one()
    member.status = MemberStatus.LEFT
    member.left_at = now()
    decrement_size(db, team.id)
    db.refresh(team)
    _record_event(db, team, actor.id, MEMBER_EVENT_LEFT, operator_id=actor.id)
    tasks = [
        _task(_team_channel(team), "team.member_left",
              {"team_id": team.id, "user_id": actor.id, "reason": "left",
               "current_size": team.current_size,
               "remaining": (team.target_size - team.current_size) if team.target_size else None}),
        _task("plaza", "plaza.changed", {"team_id": team.id, "kind": "refresh"}),
        # 退队者的存活 WS 连接立即从队伍频道摘除
        _kick_task(team, actor.id),
    ]
    if team.leader_id != actor.id:
        tasks.append(_notify(
            db, team.leader_id, NOTIFY_MEMBER_LEFT,
            {"team_id": team.id, "team_name": team.name,
             "member_nickname": actor.nickname, "current_size": team.current_size},
            team_id=team.id,
        ))
    return tasks


def e_member_kicked(db, team, actor, payload, chain) -> list[dict]:
    target_id = int(payload["target_user_id"])
    member = db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team.id, TeamMember.user_id == target_id,
            TeamMember.status == MemberStatus.ACTIVE,
        )
    ).scalar_one()
    member.status = MemberStatus.KICKED
    member.left_at = now()
    decrement_size(db, team.id)
    db.refresh(team)
    _record_event(db, team, target_id, MEMBER_EVENT_KICKED,
                  operator_id=actor.id, note="队长移出")
    tasks = [
        _task(_team_channel(team), "team.member_left",
              {"team_id": team.id, "user_id": target_id, "reason": "kicked",
               "current_size": team.current_size,
               "remaining": (team.target_size - team.current_size) if team.target_size else None}),
        _task("plaza", "plaza.changed", {"team_id": team.id, "kind": "refresh"}),
        # 被踢者的存活 WS 连接立即从队伍频道摘除（个人频道保留，"被移出"通知仍可送达）
        _kick_task(team, target_id),
    ]
    tasks.append(_notify(db, target_id, NOTIFY_KICKED,
                         {"team_id": team.id, "team_name": team.name}, team_id=team.id))
    return tasks


def e_disband(db, team, actor, payload, chain) -> list[dict]:
    team.failed_at = now()
    team.fail_reason = FailReason.DISBANDED
    tasks = []
    for m in _active_members(db, team):
        if m.user_id != actor.id:
            tasks.append(_notify(db, m.user_id, NOTIFY_TEAM_FAILED,
                                 {"team_id": team.id, "team_name": team.name,
                                  "reason": FailReason.DISBANDED},
                                 team_id=team.id))
    return tasks + _status_tasks(team)


def e_close_invite(db, team, actor, payload, chain) -> list[dict]:
    team.invite_open = False
    return []


def e_expire(db, team, actor, payload, chain) -> list[dict]:
    """招募超时下架：过期未满员不再永久挂在广场。"""
    team.failed_at = now()
    team.fail_reason = FailReason.EXPIRED
    tasks = []
    for m in _active_members(db, team):
        if m.user_id != actor.id:
            tasks.append(_notify(db, m.user_id, NOTIFY_TEAM_FAILED,
                                 {"team_id": team.id, "team_name": team.name,
                                  "reason": FailReason.EXPIRED},
                                 team_id=team.id))
    return tasks + [
        *_status_tasks(team),
        _task("plaza", "plaza.changed", {"team_id": team.id, "kind": "closed"}),
    ]


def e_form(db, team, actor, payload, chain) -> list[dict]:
    """★ 自动成团：关报名（状态变更即生效）+ 预生成核销码 + 建群欢迎消息 + 通知"""
    team.formed_at = now()
    members = _active_members(db, team)
    for m in members:
        db.add(Checkin(team_id=team.id, user_id=m.user_id, checkin_code=secrets.token_hex(8)))
    db.add(Message(
        team_id=team.id, sender_id=None, msg_type="system",
        content=f"队伍已满 {team.target_size} 人，自动成团！专属群聊已创建，"
                f"大家可以在这里协商到店时间与细节~",
    ))
    tasks = []
    for m in members:
        tasks.append(_notify(db, m.user_id, NOTIFY_FORMED,
                             {"team_id": team.id, "team_name": team.name}, team_id=team.id))
    return tasks + [
        _task(_team_channel(team), "team.formed", {"team_id": team.id, "group_created": True}),
        *_status_tasks(team),
        _task("plaza", "plaza.changed", {"team_id": team.id, "kind": "full"}),
    ]


def e_checkin(db, team, actor, payload, chain) -> list[dict]:
    row = db.execute(
        select(Checkin).where(Checkin.team_id == team.id, Checkin.user_id == actor.id)
    ).scalar_one()
    row.checked_at = now()
    rows = guards.checkin_rows_for_active(db, team)
    checked = sum(1 for r in rows if r.checked_at is not None)
    tasks = [
        _task(_team_channel(team), "checkin.updated",
              {"team_id": team.id, "checked": checked, "total": len(rows),
               "who": user_public(actor)})
    ]
    if guards.checkin_window_closed(db, team):
        try:
            tasks += chain(TeamEvent.AUTO_BILL_LOCK)
        except GuardRejected:
            pass  # 账单未录入：锁定推迟到队长录入时补触发
    return tasks


def e_submit_bill(db, team, actor, payload, chain) -> list[dict]:
    amount = Decimal(str(payload["total_amount"])).quantize(Decimal("0.01"))
    bill = _get_bill(db, team)
    if bill is None:
        bill = Bill(team_id=team.id, total_amount=amount, status=BillStatus.PENDING)
        db.add(bill)
        db.flush()
    else:
        bill.total_amount = amount
        if bill.status == BillStatus.VOID:
            bill.status = BillStatus.PENDING
    tasks = [_task(_team_channel(team), "bill.updated",
                   {"team_id": team.id,
                    "bill": {"status": bill.status, "total_amount": float(amount)}})]
    # 录入即通知队员（账单尚未生效，此时知道金额便于当场核对）
    for m in _active_members(db, team):
        if m.user_id == actor.id:
            continue
        tasks.append(_notify(
            db, m.user_id, NOTIFY_BILL_SUBMITTED,
            {"team_id": team.id, "team_name": team.name, "total_amount": float(amount)},
            team_id=team.id,
        ))
    if guards.checkin_window_closed(db, team):
        try:
            tasks += chain(TeamEvent.AUTO_BILL_LOCK)
        except GuardRejected:
            pass
    return tasks


def e_bill_locked(db, team, actor, payload, chain) -> list[dict]:
    """★ 账单生效：per_capita 快照 + 按**实际到场者**生成支付记录（队长补差保账目平衡）。

    缺席者不参与分账——原实现要求"全员到场才锁账"，一人不来即全队死锁。
    若无人到场（宽限期已过），退回按全部活跃成员分摊，避免生成空账单。
    """
    bill = _get_bill(db, team)
    members = _active_members(db, team)
    attended_ids = set(guards.attended_member_ids(db, team))
    payers = [m for m in members if m.user_id in attended_ids] or members

    total = Decimal(str(bill.total_amount))
    n = len(payers)
    per_capita = (total / n).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    bill.status = BillStatus.LOCKED
    bill.per_capita = per_capita
    bill.effective_at = now()

    tasks = []
    for m in payers:
        # 队长份额补差：total - per*(n-1)，保证账目必平
        amount = total - per_capita * (n - 1) if m.user_id == team.leader_id else per_capita
        db.add(Payment(bill_id=bill.id, user_id=m.user_id, amount=amount,
                       status=PaymentStatus.UNPAID))
        tasks.append(_notify(db, m.user_id, NOTIFY_BILL_EFFECTIVE,
                             {"team_id": team.id, "team_name": team.name,
                              "per_capita": float(per_capita),
                              "attended": len(attended_ids)},
                             team_id=team.id))
    return tasks + [
        _task(_team_channel(team), "bill.updated",
              {"team_id": team.id,
               "bill": {"status": bill.status, "per_capita": float(per_capita),
                        "payer_count": n}}),
    ]


def e_pay(db, team, actor, payload, chain) -> list[dict]:
    bill = _get_bill(db, team)
    row = db.execute(
        select(Payment).where(Payment.bill_id == bill.id, Payment.user_id == actor.id)
    ).scalar_one()
    row.status = PaymentStatus.PAID
    row.paid_at = now()
    row.mock_txn_id = f"mock_{secrets.token_hex(12)}"
    rows = db.execute(select(Payment).where(Payment.bill_id == bill.id)).scalars().all()
    paid = sum(1 for r in rows if r.status == PaymentStatus.PAID)
    tasks = [
        _task(_team_channel(team), "pay.updated",
              {"team_id": team.id, "bill_id": bill.id, "paid_count": paid,
               "total_members": len(rows), "who": user_public(actor)})
    ]
    if guards.all_payments_paid(db, team):
        try:
            tasks += chain(TeamEvent.AUTO_COMPLETE)
        except GuardRejected:
            pass
    return tasks


def e_complete(db, team, actor, payload, chain) -> list[dict]:
    team.completed_at = now()
    bill = _get_bill(db, team)
    if bill is not None:
        bill.status = BillStatus.SETTLED
        bill.settled_at = now()
    tasks = []
    for m in _active_members(db, team):
        tasks.append(_notify(db, m.user_id, NOTIFY_TEAM_COMPLETED,
                             {"team_id": team.id, "team_name": team.name}, team_id=team.id))
    return tasks + _status_tasks(team)


def e_abort(db, team, actor, payload, chain) -> list[dict]:
    bill = _get_bill(db, team)
    if bill is not None:
        bill.status = BillStatus.VOID
    team.failed_at = now()
    team.fail_reason = FailReason.CHECKIN_ABORTED
    tasks = []
    for m in _active_members(db, team):
        if m.user_id != actor.id:
            tasks.append(_notify(db, m.user_id, NOTIFY_TEAM_FAILED,
                                 {"team_id": team.id, "team_name": team.name,
                                  "reason": FailReason.CHECKIN_ABORTED},
                                 team_id=team.id))
    return tasks + _status_tasks(team)
