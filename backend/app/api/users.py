from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.requests import ConsentIn, ProfileIn, RealnameIn
from app.schemas.serializers import user_me
from app.services import report_service, user_service

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return user_me(user)


@router.patch("/me")
def update_profile(data: ProfileIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user_service.update_profile(db, user, data)
    return user_me(user)


@router.post("/me/consent")
def accept_consent(data: ConsentIn, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    """首启同意门：记录用户同意的协议版本（PIPL 可回溯）"""
    user_service.record_consent(db, user, data.version)
    return user_me(user)


@router.post("/me/realname")
def submit_realname(data: RealnameIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user_service.submit_realname(db, user, data)
    return user_me(user)


@router.delete("/me")
def delete_account(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """注销账号：匿名化个人信息 + 全部 token 立即失效（PIPL 删除权）"""
    return user_service.delete_account(db, user)


@router.get("/me/teams")
def my_teams(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return user_service.my_teams(db, user)


@router.get("/me/blocks")
def list_blocks(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {"blocked_user_ids": report_service.blocked_ids(db, user.id)}
