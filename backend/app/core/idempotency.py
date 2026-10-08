"""幂等键执行器：把"重复提交"变成"回放首次结果"。

用法（API 层）：
    return run_idempotent(db, user, request, "teams.join", lambda: team_service.join(...))

客户端在变更类请求上带 `Idempotency-Key: <uuid>`；不带则退化为原行为
（状态机本身的 409 兜底仍然生效）。
"""

import json
from typing import Any, Callable

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.idempotency import IdempotencyKey

HEADER = "Idempotency-Key"


def _load(db: Session, user_id: int, key: str) -> dict | None:
    row = db.execute(
        select(IdempotencyKey).where(
            IdempotencyKey.user_id == user_id, IdempotencyKey.key == key
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    try:
        payload = json.loads(row.response)
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


def run_idempotent(db: Session, user, request: Request, endpoint: str,
                   fn: Callable[[], Any]) -> Any:
    key = (request.headers.get(HEADER) or "").strip()
    if not key or user is None:
        return fn()

    cached = _load(db, user.id, key)
    if cached is not None:
        # 回放首次响应，避免"重复提交"造成二次业务动作
        return cached

    result = fn()

    try:
        db.add(IdempotencyKey(
            user_id=user.id, key=key[:64], endpoint=endpoint[:80],
            response=json.dumps(result, ensure_ascii=False, default=str),
        ))
        db.commit()
    except IntegrityError:
        # 并发同键：另一个请求已写入，回滚本次记录即可（业务动作已由状态机保证唯一）
        db.rollback()
    except Exception:
        db.rollback()
    return result
