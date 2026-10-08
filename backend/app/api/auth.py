from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core import ratelimit
from app.core.deps import get_current_user, get_db
from app.core.config import settings
from app.models.user import User
from app.schemas.requests import AlipayLoginIn, LoginIn, RegisterIn
from app.schemas.serializers import user_me
from app.services import auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return user_me(user)


@router.post("/register")
def register(data: RegisterIn, request: Request, db: Session = Depends(get_db)):
    # 防批量注册刷号（原实现无任何限流）
    ratelimit.check("auth", ratelimit.client_ip(request), settings.RATE_LIMIT_AUTH_PER_MIN)
    return auth_service.register(db, data)


@router.post("/login")
def login(data: LoginIn, request: Request, db: Session = Depends(get_db)):
    # 防口令爆破
    ratelimit.check("auth", ratelimit.client_ip(request), settings.RATE_LIMIT_AUTH_PER_MIN)
    return auth_service.login(db, data)


@router.post("/alipay")
def alipay_login(data: AlipayLoginIn, request: Request, db: Session = Depends(get_db)):
    """小程序授权登录。MVP mock：code = "mock:<username>" """
    ratelimit.check("auth", ratelimit.client_ip(request), settings.RATE_LIMIT_AUTH_PER_MIN)
    return auth_service.alipay_login(db, data)
