"""状态机引擎统一入口。所有状态变更必须经由 dispatch()，保证守卫/副作用/链式触发一致执行。"""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.agent.events import TeamEvent
from app.agent.states import TeamStatus


class TransitionForbidden(Exception):
    """当前状态不允许该事件（如成团后解散）"""

    def __init__(self, status: str, event: str):
        self.status = status
        self.event = event
        super().__init__(f"当前状态 {status} 不允许执行 {event}")


class GuardRejected(Exception):
    """守卫条件不满足"""

    def __init__(self, message: str, status_code: int = 403):
        self.status_code = status_code
        super().__init__(message)


@dataclass
class Rule:
    guards: tuple = field(default_factory=tuple)
    effects: tuple = field(default_factory=tuple)
    next_state: str | None = None  # TeamStatus.value


def dispatch(db: Session, team, event, actor, payload: dict | None = None) -> list[dict]:
    """执行一次状态流转，返回待入队 task_queue 的任务列表。

    key 一律用 .value 字符串，规避 str-Enum 的 hash 陷阱。
    """
    from app.agent.transitions import TRANSITIONS

    key = (TeamStatus(team.status).value, TeamEvent(event).value)
    rule = TRANSITIONS.get(key)
    if rule is None:
        raise TransitionForbidden(TeamStatus(team.status).value, TeamEvent(event).value)

    for guard in rule.guards:
        ok, msg, code = guard(db, team, actor, payload or {})
        if not ok:
            raise GuardRejected(msg, code or 403)

    if rule.next_state is not None:
        team.status = rule.next_state

    def chain(next_event: TeamEvent) -> list[dict]:
        return dispatch(db, team, next_event, actor, payload)

    tasks: list[dict] = []
    for effect in rule.effects:
        tasks.extend(effect(db, team, actor, payload or {}, chain) or [])
    return tasks
