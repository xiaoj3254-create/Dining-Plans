from typing import Optional

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session

from app.core import ratelimit, uploads
from app.core.config import settings
from app.core.deps import get_db, require_active, require_verified
from app.models.user import User
from app.schemas.requests import MessageIn
from app.services import chat_service

router = APIRouter(prefix="/api/teams", tags=["chat"])


@router.get("/{team_id}/messages")
def list_messages(
    team_id: int,
    before_id: Optional[int] = None,
    limit: int = Query(20, ge=1, le=50),
    user: User = Depends(require_verified),
    db: Session = Depends(get_db),
):
    return chat_service.list_messages(db, team_id, user, before_id, limit)


@router.post("/{team_id}/messages")
def send_message(
    team_id: int,
    data: MessageIn,
    user: User = Depends(require_active),
    db: Session = Depends(get_db),
):
    # 洪水防护（群聊无需幂等键：重复发送不产生资金/名额类副作用）
    ratelimit.check("message", user.id, settings.RATE_LIMIT_MESSAGE_PER_MIN)
    return chat_service.send_message(
        db, team_id, user, data.content,
        msg_type=data.msg_type, mentions_all=data.mentions_all,
    )


@router.post("/{team_id}/uploads")
def upload_chat_image(
    team_id: int,
    file: UploadFile = File(...),
    user: User = Depends(require_active),
    db: Session = Depends(get_db),
):
    """群聊图片上传（先上传拿 URL，再以 msg_type=image 发消息）。"""
    ratelimit.check("upload", user.id, settings.UPLOAD_PER_MIN)
    # 复用群聊的可见性与阶段校验：非成员、未成团都不允许上传
    chat_service.ensure_can_chat(db, team_id, user)
    return uploads.save_image(file, subdir="chat")


@router.post("/{team_id}/messages/{message_id}/recall")
def recall_message(
    team_id: int,
    message_id: int,
    user: User = Depends(require_active),
    db: Session = Depends(get_db),
):
    """撤回本人消息（发送后 2 分钟内）"""
    return chat_service.recall_message(db, team_id, message_id, user)
