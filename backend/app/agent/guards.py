"""状态机守卫条件。签名统一：(db, team, actor, payload) -> (ok, msg, status_code|None)。

status_code 供 API 层映射 HTTP 状态：None→403；409 用于资源冲突（满员等）；
422 用于业务字段不合法。

本次修复要点：
- `g_publish_fields` 不再依赖真值判断（原实现被 `datetime.max` 哨兵绕过）；
- `g_not_member` 对被踢用户生效（踢人不再形同虚设）；
- 新增 `g_not_blocked`（跨队拉黑）；
- 核销与分账一律以 **active 成员** 为口径，成团后退队者不参与分摊；
- `g_bill_lockable` 改为"账单已录 + 核销窗口已关闭"，不再是"必须全员到场"。
"""

from datetime import timedelta

from sqlalchemy import select

from app.agent.concurrency import try_increment_size
from app.agent.states import BillStatus, MemberRole, MemberStatus, TeamMode
from app.core.config import settings
from app.core.timeutil import now
from app.models.bill import Bill
from app.models.block import UserBlock
from app.models.checkin import Checkin
from app.models.member import TeamMember
from app.models.payment import Payment
from app.models.user import User


def _active_member(db, team, user_id) -> TeamMember | None:
    return db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team.id,
            TeamMember.user_id == user_id,
            TeamMember.status == MemberStatus.ACTIVE,
        )
    ).scalar_one_or_none()


def _get_bill(db, team) -> Bill | None:
    return db.execute(select(Bill).where(Bill.team_id == team.id)).scalar_one_or_none()


def _member_row(db, team, user_id) -> TeamMember | None:
    """任意状态的成员行（含 left/kicked），用于冷却判定。"""
    return db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team.id, TeamMember.user_id == user_id
        )
    ).scalar_one_or_none()


# ---------- 通用 ----------

def g_is_leader(db, team, actor, payload):
    if actor.id != team.leader_id:
        return False, "仅队长可执行此操作", 403
    return True, "", None


def g_not_member(db, team, actor, payload):
    """非成员才能报名；被队长踢出过的用户在该队范围内进入冷却，不能原地重报。"""
    existing = _member_row(db, team, actor.id)
    if existing is not None and existing.status == MemberStatus.ACTIVE:
        return False, "你已是该队成员", 409
    if existing is not None and existing.status == MemberStatus.KICKED:
        return False, "你已被队长移出该队伍，无法再次加入", 403
    return True, "", None


def g_not_blocked(db, team, actor, payload):
    """跨队拉黑：双方任一侧存在拉黑关系即拒绝入队。"""
    row = db.execute(
        select(UserBlock).where(
            ((UserBlock.blocker_id == team.leader_id) & (UserBlock.blocked_id == actor.id))
            | ((UserBlock.blocker_id == actor.id) & (UserBlock.blocked_id == team.leader_id))
        )
    ).scalars().first()
    if row is not None:
        return False, "你与该队队长之间存在拉黑关系，无法加入", 403
    return True, "", None


def g_invite_entry(db, team, actor, payload):
    """模式二链接报名入口校验"""
    if team.mode != TeamMode.INVITE:
        return False, "该队伍不支持链接邀请", 403
    if not team.invite_open:
        return False, "队长已关闭链接邀请", 403
    code = (payload or {}).get("code") or ""
    if code != team.code:
        return False, "邀请码无效", 403
    return True, "", None


def g_slot_available(db, team, actor, payload):
    """★ 原子抢名额（本守卫带写副作用，必须是最后一个守卫）"""
    if not try_increment_size(db, team.id):
        return False, "队伍已满员或已关闭报名", 409
    return True, "", None


def g_is_full(db, team, actor, payload):
    """链式成团守卫：仅判断满员，不做名额扣减"""
    if team.target_size is None or team.current_size < team.target_size:
        return False, "队伍未满员", 409
    return True, "", None


def g_slot_available_formed(db, team, actor, payload):
    """★ 成团后补招占位（带写副作用，必须是最后一个守卫）"""
    from app.agent.concurrency import try_increment_size_for_formed

    if not try_increment_size_for_formed(db, team.id):
        return False, "队伍名额已满或阵容已锁定", 409
    return True, "", None


def g_fill_seat_target(db, team, actor, payload):
    """补招对象校验：必须实名、未在队内、未被本队踢过。"""
    target_id = int((payload or {}).get("target_user_id") or 0)
    if target_id == actor.id:
        return False, "不能补招自己", 400
    target = db.get(User, target_id)
    if target is None:
        return False, "目标用户不存在", 404
    if not target.real_name_verified:
        return False, "该用户尚未完成实名认证", 422
    existing = _member_row(db, team, target_id)
    if existing is not None and existing.status == MemberStatus.ACTIVE:
        return False, "该用户已是队伍成员", 409
    if existing is not None and existing.status == MemberStatus.KICKED:
        return False, "该用户曾被移出本队，不可再补招", 403
    return True, "", None


# ---------- 退出/踢人 ----------

def g_member_not_leader(db, team, actor, payload):
    member = _active_member(db, team, actor.id)
    if member is None:
        return False, "你不是该队成员", 403
    if member.role == MemberRole.LEADER:
        return False, "队长不可退出队伍，成团前可解散", 403
    return True, "", None


def g_leave_window_open(db, team, actor, payload):
    """成团后仅在账单生效前允许退出，避免锁定后"退队逃单"。"""
    bill = _get_bill(db, team)
    if bill is not None and bill.status in (BillStatus.LOCKED, BillStatus.SETTLED):
        return False, "账单已生效，不可退出队伍", 409
    return True, "", None


def g_kick_target(db, team, actor, payload):
    target_id = int((payload or {}).get("target_user_id") or 0)
    if target_id == actor.id:
        return False, "不能踢出自己", 400
    target = _active_member(db, team, target_id)
    if target is None:
        return False, "目标不是活跃队员", 404
    if target.role == MemberRole.LEADER:
        return False, "不能踢出队长", 403
    return True, "", None


# ---------- 发布 ----------

def g_publish_fields(db, team, actor, payload):
    """发布必填校验。
    原实现用 `not team.dining_time` 判空，而建队时缺省会写入 datetime.max 哨兵，
    真值恒为 True → 校验被完全绕过（实测可发布出 9999-12-31 的饭局）。
    现改为显式 None 判定 + 目标人数下限。
    """
    missing = []
    if not (team.name or "").strip():
        missing.append("队伍名")
    if team.target_size is None:
        missing.append("目标人数")
    if not (team.cuisine_type or "").strip():
        missing.append("就餐品类")
    if team.restaurant_id is None:
        missing.append("餐馆")
    if team.dining_time is None:
        missing.append("就餐时间")
    if missing:
        return False, "必填项缺失：" + "/".join(missing), 422
    if team.target_size < 2:
        return False, "目标人数至少 2 人", 422
    if team.dining_time <= now():
        return False, "计划就餐时间必须晚于当前时间", 422
    return True, "", None


# ---------- 招募期修改（队长在招募中调整饭局） ----------

def g_recruiting_edit(db, team, actor, payload):
    """招募期修改的额外约束。

    草稿期随便改；一旦发布并有人报名，就要防止把队伍改到不合法/不可预期的状态：
    - 目标人数不得小于已入队人数（否则直接违反 DB 的 ck_teams_no_oversell）；
    - 组队模式不允许改（匿名 ↔ 链接邀请会改变报名入口语义与已发出去的邀请码）；
    - 若改就餐时间，必须仍在未来（否则等于把队伍改成"已过期"）。
    """
    data = payload or {}
    size = data.get("target_size")
    if size is not None and team.current_size is not None and size < team.current_size:
        return False, f"目标人数不能小于已入队人数（当前 {team.current_size} 人）", 422
    if data.get("mode") is not None and data["mode"] != team.mode:
        return False, "已发布的饭局不可更改组队模式", 422
    when = data.get("dining_time")
    if when is not None and when <= now():
        return False, "计划就餐时间必须晚于当前时间", 422
    return True, "", None


# ---------- 核销 / 账单 / 支付 ----------

def g_checkin_code(db, team, actor, payload):
    code = (payload or {}).get("checkin_code") or ""
    row = db.execute(
        select(Checkin).where(Checkin.team_id == team.id, Checkin.user_id == actor.id)
    ).scalar_one_or_none()
    if row is None:
        return False, "核销记录不存在", 404
    if row.checked_at is not None:
        return False, "你已完成到场确认", 409
    if code != row.checkin_code:
        return False, "核销码不正确", 403
    # 账单生效后核销窗口关闭：防止锁账后补核销"到场不付钱"
    bill = _get_bill(db, team)
    if bill is not None and bill.status in (BillStatus.LOCKED, BillStatus.SETTLED):
        return False, "账单已生效，到场确认已截止", 409
    return True, "", None


def g_bill_amount(db, team, actor, payload):
    amount = (payload or {}).get("total_amount")
    if amount is None or amount <= 0:
        return False, "账单总额必须大于 0", 422
    return True, "", None


def g_bill_editable(db, team, actor, payload):
    """账单已生效（LOCKED/SETTLED）后禁止再次提交修改，避免重复生成支付记录"""
    bill = _get_bill(db, team)
    if bill is not None and bill.status in (BillStatus.LOCKED, BillStatus.SETTLED):
        return False, "账单已生效，不可修改金额", 409
    return True, "", None


def g_bill_lockable(db, team, actor, payload):
    """账单生效条件：账单已录入 + 到场确认窗口已关闭。

    放宽点：不再要求"全员到场"。只要核销窗口关闭（全员确认 或 已过宽限期），
    就按**实际到场人数**分摊，缺席者不参与分账——否则一人不来全队永远锁不了账。
    """
    bill = _get_bill(db, team)
    if bill is None or bill.total_amount is None:
        return False, "账单尚未录入，账单生效推迟到队长录入后自动触发", 409
    if not checkin_window_closed(db, team):
        return False, "到场确认尚未截止，账单生效推迟到核销截止后自动触发", 409
    return True, "", None


def g_unpaid_payment(db, team, actor, payload):
    bill = _get_bill(db, team)
    if bill is None or bill.status != BillStatus.LOCKED:
        return False, "账单未生效，暂不可支付", 409
    row = db.execute(
        select(Payment).where(Payment.bill_id == bill.id, Payment.user_id == actor.id)
    ).scalar_one_or_none()
    if row is None:
        return False, "支付记录不存在（你未参与本次分摊）", 404
    if row.status != "unpaid":
        return False, "你已完成支付", 409
    return True, "", None


def g_all_paid(db, team, actor, payload):
    """链式完成守卫：所有支付记录均已结清"""
    if not all_payments_paid(db, team):
        return False, "尚有未结清款项", 409
    return True, "", None


def g_abort_allowed(db, team, actor, payload):
    """核销异常解散：仅当尚无任何成功支付（钱未动）时允许，避免退款问题"""
    bill = _get_bill(db, team)
    if bill is not None:
        paid = db.execute(
            select(Payment).where(Payment.bill_id == bill.id, Payment.status == "paid")
        ).scalars().first()
        if paid is not None:
            return False, "已有成员完成支付，不可解散重开", 409
    return True, "", None


def g_expired(db, team, actor, payload):
    """链式/巡检超时守卫：就餐时间 + 宽限期已过。"""
    if team.dining_time is None:
        return False, "未设置就餐时间", 409
    if settings.RECRUITING_EXPIRE_GRACE_HOURS <= 0:
        return False, "未启用招募超时", 409
    deadline = team.dining_time + timedelta(hours=settings.RECRUITING_EXPIRE_GRACE_HOURS)
    if now() < deadline:
        return False, "尚未到招募截止时间", 409
    return True, "", None


# ---------- 断言辅助（供服务层复用） ----------

def active_member_ids(db, team) -> list[int]:
    """当前活跃成员 id（核销/分账的唯一口径）。"""
    return list(
        db.execute(
            select(TeamMember.user_id).where(
                TeamMember.team_id == team.id, TeamMember.status == MemberStatus.ACTIVE
            )
        ).scalars().all()
    )


def checkin_rows_for_active(db, team) -> list[Checkin]:
    ids = active_member_ids(db, team)
    if not ids:
        return []
    return list(
        db.execute(
            select(Checkin).where(
                Checkin.team_id == team.id, Checkin.user_id.in_(ids)
            )
        ).scalars().all()
    )


def attended_member_ids(db, team) -> list[int]:
    """已确认到场的活跃成员 id。"""
    return [r.user_id for r in checkin_rows_for_active(db, team) if r.checked_at is not None]


def all_members_checked(db, team) -> bool:
    """活跃成员是否全部完成到场确认（无人到场时为 False）。"""
    ids = active_member_ids(db, team)
    rows = checkin_rows_for_active(db, team)
    if not ids or not rows:
        return False
    return len(rows) == len(ids) and all(r.checked_at is not None for r in rows)


def checkin_window_closed(db, team) -> bool:
    """到场确认窗口是否已关闭：全员确认，或已过就餐时间 + 宽限期。"""
    if all_members_checked(db, team):
        return True
    if settings.CHECKIN_GRACE_HOURS > 0 and team.dining_time is not None:
        deadline = team.dining_time + timedelta(hours=settings.CHECKIN_GRACE_HOURS)
        if now() >= deadline:
            return True
    return False


def all_payments_paid(db, team) -> bool:
    bill = _get_bill(db, team)
    if bill is None:
        return False
    rows = db.execute(select(Payment).where(Payment.bill_id == bill.id)).scalars().all()
    return len(rows) > 0 and all(r.status == "paid" for r in rows)
