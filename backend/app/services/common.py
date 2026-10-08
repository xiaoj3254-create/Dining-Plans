"""服务层公共工具：任务入队、队伍获取、成员断言。"""

import json

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agent.engine import GuardRejected, TransitionForbidden
from app.agent.states import MemberStatus
from app.models.member import TeamMember
from app.models.task import TaskQueue
from app.models.team import Team
from app.models.user import User


def get_team_or_404(db: Session, team_id: int) -> Team:
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="队伍不存在")
    return team


def enqueue(db: Session, tasks: list[dict]) -> None:
    """状态机产生的副作用任务落 task_queue（同事务），由后台 worker 消费"""
    for t in tasks:
        db.add(TaskQueue(kind=t["kind"], payload=json.dumps(t["payload"], ensure_ascii=False)))


def dispatch_and_enqueue(db: Session, team: Team, event, actor: User, payload: dict | None = None) -> Team:
    """统一封装：dispatch → 任务入队 → 异常映射 HTTP。

    约定：业务拒绝一律 403/409/422，**不出现 500**。因此 DB 层约束冲突
    （唯一索引等）也必须映射为 409，而不是穿透成 500。
    """
    from app.agent.engine import dispatch

    try:
        tasks = dispatch(db, team, event, actor, payload)
        enqueue(db, tasks)
        db.flush()
    except TransitionForbidden as e:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(e))
    except GuardRejected as e:
        db.rollback()
        raise HTTPException(status_code=e.status_code, detail=str(e))
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="操作冲突：该资源已被并发修改，请刷新后重试")
    return team


def active_member(db: Session, team_id: int, user_id: int) -> TeamMember | None:
    return db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == user_id,
            TeamMember.status == MemberStatus.ACTIVE,
        )
    ).scalar_one_or_none()


def assert_active_member(db: Session, team_id: int, user_id: int) -> TeamMember:
    """队伍资源读写的统一入口：非活跃成员一律 403。"""
    member = active_member(db, team_id, user_id)
    if member is None:
        raise HTTPException(status_code=403, detail="仅队伍成员可执行此操作")
    return member


def assert_leader(db: Session, team: Team, user: User) -> None:
    if team.leader_id != user.id:
        raise HTTPException(status_code=403, detail="仅队长可执行此操作")


def assert_not_restricted(user: User) -> None:
    """举报累计触发限制后，禁止发起/报名/发消息。"""
    if user.restricted_at is not None:
        reason = user.restricted_reason or "存在违规行为"
        raise HTTPException(status_code=403, detail=f"账号已被限制使用组队功能（{reason}）")


def get_user_or_404(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user


class SystemActor:
    """巡检 / 自动事件的虚拟操作者。

    注意：不能用 `User.__new__(User)` —— 那会绕过 SQLAlchemy 的实例化，
    访问/赋值属性时抛 `_sa_instance_state` 缺失，导致巡检静默失败
    （初期正是这个原因让"到期锁账"和"招募超时下架"两个巡检都没生效）。

    id = -1 不与任何真实用户相等，因此 e_expire / e_disband 等
    "通知除操作者以外的所有人"的循环会覆盖包括队长在内的全部成员。
    """

    def __init__(self) -> None:
        self.id = -1
        self.username = "system"
        self.nickname = "系统"
        self.age = 0
        self.gender = "other"
        self.real_name_verified = True
        self.restricted_at = None
        self.deleted_at = None


def system_actor() -> SystemActor:
    return SystemActor()
