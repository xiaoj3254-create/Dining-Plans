from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.models.user import User

_bearer = HTTPBearer(auto_error=False)


def get_db():
    from app import db as database  # 运行时取，保证测试重初始化后生效

    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _user_from_token(db: Session, token: str) -> User:
    """token → User，同时校验版本号（注销/强制下线后旧 token 立即失效）。"""
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    try:
        user_id = int(payload["sub"])
        token_ver = int(payload.get("ver", 0))
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="登录凭证无效，请重新登录")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在")
    if token_ver != (user.token_version or 0):
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")
    return user


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="未登录")
    return _user_from_token(db, credentials.credentials)


def require_verified(user: User = Depends(get_current_user)) -> User:
    """实名强校验：未实名用户无法使用任何核心组队功能"""
    if not user.real_name_verified:
        raise HTTPException(status_code=403, detail="请先完成实名认证")
    return user


def require_active(user: User = Depends(require_verified)) -> User:
    """实名 + 未被限制：举报累计触发限制后禁止发起/报名/发消息。"""
    if user.restricted_at is not None:
        reason = user.restricted_reason or "存在违规行为"
        raise HTTPException(status_code=403, detail=f"账号已被限制使用组队功能（{reason}），如有疑问请联系客服")
    return user


def get_ws_user(token: str):
    """WebSocket 鉴权：返回 (user, error_msg)"""
    from app.db import SessionLocal as SL

    payload = decode_token(token)
    if payload is None:
        return None, "登录已过期"
    try:
        user_id = int(payload["sub"])
        token_ver = int(payload.get("ver", 0))
    except (KeyError, TypeError, ValueError):
        return None, "登录凭证无效"
    db: Session = SL()
    try:
        user = db.get(User, user_id)
        if user is None:
            return None, "用户不存在"
        if token_ver != (user.token_version or 0):
            return None, "登录已失效"
        return user, None
    finally:
        db.close()
