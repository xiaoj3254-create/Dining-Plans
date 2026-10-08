from enum import Enum


class TeamStatus(str, Enum):
    DRAFT = "draft"
    RECRUITING = "recruiting"
    FORMED = "formed"
    COMPLETED = "completed"
    FAILED = "failed"


class MemberRole:
    LEADER = "leader"
    MEMBER = "member"


class MemberStatus:
    ACTIVE = "active"
    LEFT = "left"
    KICKED = "kicked"


class BillStatus:
    PENDING = "pending"
    LOCKED = "locked"
    SETTLED = "settled"
    VOID = "void"


class PaymentStatus:
    UNPAID = "unpaid"
    PAID = "paid"


class TeamMode:
    ANONYMOUS = "anonymous"
    INVITE = "invite"


class FailReason:
    """队伍失败归因（写入 teams.fail_reason，供运营与纠纷复盘）"""

    DISBANDED = "disbanded"            # 队长主动解散
    CHECKIN_ABORTED = "checkin_aborted"  # 核销异常，解散重开
    EXPIRED = "expired"                # 招募超时，未满员自动关闭
    USER_DELETED = "user_deleted"      # 队长注销导致的清理
