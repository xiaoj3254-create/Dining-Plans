import secrets

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.config import settings
from app.core.security import create_token, hash_password, verify_password
from app.core.timeutil import now
from app.models.user import User


def _issue(user: User) -> dict:
    from app.schemas.serializers import user_me

    return {
        "access_token": create_token(user.id, user.token_version or 0),
        "user": user_me(user),
    }


def _accept_consent(user: User, agreed: bool) -> None:
    """记录协议同意（版本号可回溯：协议文本更新时 user.consent_version 会落后于当前版本）。"""
    if agreed and user.consent_version is None:
        user.consent_version = settings.CONSENT_VERSION
        user.consent_at = now()


def register(db: Session, data) -> dict:
    # PIPL：未取得同意不得处理个人信息，注册必须显式同意
    if not data.consent:
        raise HTTPException(
            status_code=422,
            detail="请先阅读并同意《用户服务协议》与《隐私政策》",
        )
    exists = db.execute(select(User.id).where(User.username == data.username)).first()
    if exists:
        raise HTTPException(status_code=409, detail="用户名已存在")
    user = User(
        username=data.username,
        password_hash=hash_password(data.password),
        nickname=data.nickname,
        age=data.age,
        gender=data.gender,
    )
    _accept_consent(user, True)
    db.add(user)
    db.flush()
    audit(db, user.id, "user.register", "user", user.id)
    db.commit()
    return _issue(user)


def login(db: Session, data) -> dict:
    user = db.execute(select(User).where(User.username == data.username)).scalar_one_or_none()
    if user is None or user.password_hash is None or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if user.deleted_at is not None:
        raise HTTPException(status_code=403, detail="该账号已注销")
    return _issue(user)


def alipay_login(db: Session, data) -> dict:
    """小程序授权登录。

    MVP 走 mock（code 格式 `mock:<username>`）；真实环境应为：
    前端 my.getAuthCode → 服务端调支付宝 oauth 换 user_id。
    注意：`settings.MOCK_ALIPAY` 在 `ENV=prod` 时会被 assert_production_ready 拒绝启动，
    避免"知道用户名即可登录他人账号"。
    """
    if not settings.MOCK_ALIPAY:
        raise HTTPException(status_code=501, detail="真实支付宝登录未配置")
    if not data.code.startswith("mock:"):
        raise HTTPException(status_code=400, detail="无效的授权码")
    username = data.code[5:].strip() or f"ap_{secrets.token_hex(4)}"
    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if user is None:
        # 新用户：必须先同意协议（首启同意门通过后前端才会带上 consent）
        if not data.consent:
            raise HTTPException(
                status_code=422,
                detail="请先阅读并同意《用户服务协议》与《隐私政策》",
            )
        user = User(
            username=username,
            nickname=data.nickname or username,
            age=data.age or 25,
            gender=data.gender or "other",
        )
        _accept_consent(user, True)
        db.add(user)
        db.flush()
        audit(db, user.id, "user.register", "user", user.id, via="alipay_mock")
        db.commit()
    elif user.deleted_at is not None:
        raise HTTPException(status_code=403, detail="该账号已注销")
    else:
        # 历史用户补记同意（协议版本升级后也能回溯到）
        if data.consent and user.consent_version is None:
            _accept_consent(user, True)
            db.commit()
    return _issue(user)
