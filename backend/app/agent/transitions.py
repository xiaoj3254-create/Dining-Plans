"""声明式流转表：key = (当前态.value, 事件.value)。

设计约束：
- g_slot_available（原子抢名额）带写副作用，必须放在守卫列表最后；
- 成团后 DISBAND 不在表内 → 引擎抛 TransitionForbidden → 409（防恶意跑路）；
- 链式触发（JOIN→AUTO_FORM、CHECKIN/SUBMIT_BILL→AUTO_BILL_LOCK、PAY→AUTO_COMPLETE）
  由副作用内部调用 chain()；
- EXPIRE 由巡检触发（attractor=rules 判定），使过期队伍不再永久占用广场。
"""

from app.agent import effects as eff
from app.agent import guards as g
from app.agent.engine import Rule
from app.agent.events import TeamEvent as E
from app.agent.states import TeamStatus as S

TRANSITIONS = {
    # ---------- 草稿态 ----------
    (S.DRAFT.value, E.UPDATE_DRAFT.value): Rule(guards=(g.g_is_leader,), effects=(eff.e_update_draft,)),
    (S.DRAFT.value, E.PUBLISH.value): Rule(
        guards=(g.g_is_leader, g.g_publish_fields), next_state=S.RECRUITING.value,
        effects=(eff.e_publish,),
    ),
    # ---------- 招募中 ----------
    (S.RECRUITING.value, E.JOIN.value): Rule(
        guards=(g.g_not_member, g.g_not_blocked, g.g_slot_available),
        effects=(eff.e_member_joined,),
    ),
    (S.RECRUITING.value, E.JOIN_BY_LINK.value): Rule(
        guards=(g.g_invite_entry, g.g_not_member, g.g_not_blocked, g.g_slot_available),
        effects=(eff.e_member_joined,),
    ),
    (S.RECRUITING.value, E.LEAVE.value): Rule(
        guards=(g.g_member_not_leader,), effects=(eff.e_member_left,),
    ),
    (S.RECRUITING.value, E.KICK.value): Rule(
        guards=(g.g_is_leader, g.g_kick_target), effects=(eff.e_member_kicked,),
    ),
    (S.RECRUITING.value, E.DISBAND.value): Rule(
        guards=(g.g_is_leader,), next_state=S.FAILED.value, effects=(eff.e_disband,),
    ),
    (S.RECRUITING.value, E.CLOSE_INVITE.value): Rule(
        guards=(g.g_is_leader,), effects=(eff.e_close_invite,),
    ),
    # 队长在招募期调整饭局（改时间/菜系/菜单/人数等）→ 通知全部队员
    (S.RECRUITING.value, E.UPDATE_DRAFT.value): Rule(
        guards=(g.g_is_leader, g.g_recruiting_edit), effects=(eff.e_update_published,),
    ),
    (S.RECRUITING.value, E.AUTO_FORM.value): Rule(
        guards=(g.g_is_full,), next_state=S.FORMED.value, effects=(eff.e_form,),
    ),
    # 招募超时：就餐时间 + 宽限期仍未满员 → 自动关闭（巡检触发）
    (S.RECRUITING.value, E.EXPIRE.value): Rule(
        guards=(g.g_expired,), next_state=S.FAILED.value, effects=(eff.e_expire,),
    ),
    # ---------- 已成团 ----------
    (S.FORMED.value, E.CHECKIN.value): Rule(
        guards=(g.g_checkin_code,), effects=(eff.e_checkin,),
    ),
    # 成团后允许队员退出，但仅限账单生效前（账单锁定后退队即逃单）
    (S.FORMED.value, E.LEAVE.value): Rule(
        guards=(g.g_member_not_leader, g.g_leave_window_open), effects=(eff.e_member_left,),
    ),
    # 队长补招：把退出释放的名额补给指定用户（替代"只能解散重开"）
    (S.FORMED.value, E.FILL_SEAT.value): Rule(
        guards=(g.g_is_leader, g.g_fill_seat_target, g.g_slot_available_formed),
        effects=(eff.e_fill_seat,),
    ),
    # 补招链接：成团后有队员退出留下空位时，邀请码持有者可直接补位
    # （没有用户目录，靠"队长把码/链接给谁"来选人；席位占满即自动失效）
    (S.FORMED.value, E.JOIN_BY_LINK.value): Rule(
        guards=(g.g_invite_entry, g.g_not_member, g.g_not_blocked, g.g_slot_available_formed),
        effects=(eff.e_fill_seat,),
    ),
    (S.FORMED.value, E.SUBMIT_BILL.value): Rule(
        guards=(g.g_is_leader, g.g_bill_editable, g.g_bill_amount), effects=(eff.e_submit_bill,),
    ),
    (S.FORMED.value, E.AUTO_BILL_LOCK.value): Rule(
        guards=(g.g_bill_lockable,), effects=(eff.e_bill_locked,),
    ),
    (S.FORMED.value, E.PAY.value): Rule(
        guards=(g.g_unpaid_payment,), effects=(eff.e_pay,),
    ),
    (S.FORMED.value, E.AUTO_COMPLETE.value): Rule(
        guards=(g.g_all_paid,), next_state=S.COMPLETED.value, effects=(eff.e_complete,),
    ),
    (S.FORMED.value, E.ABORT.value): Rule(
        guards=(g.g_is_leader, g.g_abort_allowed), next_state=S.FAILED.value, effects=(eff.e_abort,),
    ),
    # 注意：(FORMED, DISBAND) 故意缺省 —— 成团后禁止解散（需求：防恶意跑路）
    # 注意：AUTO_FORM / AUTO_COMPLETE / AUTO_BILL_LOCK 是链式内部事件，不校验角色
}
