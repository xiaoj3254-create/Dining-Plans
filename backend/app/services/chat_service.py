"""群聊服务。

本次修复要点：
- 发送前做内容安全检查（原实现任意文本原样入库并广播）；
- 支持 2 分钟内撤回（误发敏感信息的补救通道）；
- 命中安全策略的记录审计，便于后续风控与举报取证。
"""

from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.states import TeamStatus
from app.core import text_guard, uploads
from app.core.audit import audit
from app.core.timeutil import now
from app.models.message import Message
from app.models.team import Team
from app.schemas.serializers import message_out
from app.services.common import assert_active_member, enqueue, get_team_or_404

RECALL_WINDOW_MINUTES = 2


def _require_formed(team: Team) -> None:
    if team.status not in (TeamStatus.FORMED.value, TeamStatus.COMPLETED.value):
        raise HTTPException(status_code=409, detail="群聊在成团后开放")


def ensure_can_chat(db: Session, team_id: int, actor) -> Team:
    """群聊准入校验（成员 + 已成团），供发消息/上传图片共用。"""
    team = get_team_or_404(db, team_id)
    assert_active_member(db, team.id, actor.id)
    _require_formed(team)
    return team


def _out(db: Session, msg, actor) -> dict:
    """消息出站：额外标注 is_me / sender_id。

    原实现前端靠"昵称相同"判断自己发的消息——只要两人昵称相同就会错位，
    撤回权限也会被误判。身份判断必须由服务端以 user_id 为准。
    sender_id 与队伍详情页的成员 user_id 同权限（仅同队成员可见），
    用于长按举报时定位被举报人。
    """
    out = message_out(db, msg)
    out["is_me"] = msg.sender_id is not None and msg.sender_id == actor.id
    out["sender_id"] = msg.sender_id
    return out


def list_messages(db: Session, team_id: int, actor, before_id: int | None, limit: int = 20) -> dict:
    team = get_team_or_404(db, team_id)
    assert_active_member(db, team.id, actor.id)
    _require_formed(team)
    q = select(Message).where(Message.team_id == team_id)
    if before_id:
        q = q.where(Message.id < before_id)
    rows = db.execute(q.order_by(Message.id.desc()).limit(limit)).scalars().all()
    rows = list(reversed(rows))
    return {
        "messages": [_out(db, m, actor) for m in rows],
        "has_more": len(rows) == limit,
    }


def send_message(db: Session, team_id: int, actor, content: str,
                 msg_type: str = "text", mentions_all: bool = False) -> dict:
    team = get_team_or_404(db, team_id)
    assert_active_member(db, team.id, actor.id)
    _require_formed(team)

    if msg_type == "image":
        # 只接受自家上传接口产出的路径：禁止外链（防盗图/防钓鱼/防跨站追踪）
        if not uploads.is_own_upload_url(content):
            raise HTTPException(status_code=422, detail="图片地址无效，请重新上传")
    else:
        msg_type = "text"
        try:
            text_guard.check_text(content)
        except text_guard.TextRejected as e:
            audit(db, actor.id, "chat.blocked", "team", team_id,
                  category=e.category, preview=content[:50])
            db.commit()
            raise HTTPException(status_code=422, detail=e.message)

    if mentions_all:
        # @全体成员属于"打扰全队"的权限，只给队长
        if actor.id != team.leader_id:
            raise HTTPException(status_code=403, detail="只有队长可以 @全体成员")
        mentions_all = True

    msg = Message(team_id=team_id, sender_id=actor.id, msg_type=msg_type,
                  content=content, mentions_all=mentions_all)
    db.add(msg)
    db.flush()  # 先取 msg.id 供广播数据使用
    out = _out(db, msg, actor)
    enqueue(db, [{
        "kind": "broadcast",
        "payload": {
            "channel": f"team:{team_id}", "event": "chat.message",
            "data": {"team_id": team_id, "message": out},
        },
    }])
    db.commit()
    return out


def recall_message(db: Session, team_id: int, message_id: int, actor) -> dict:
    """撤回本人消息（2 分钟内）。撤回后各端通过广播拿到替换后的内容。"""
    team = get_team_or_404(db, team_id)
    assert_active_member(db, team.id, actor.id)
    msg = db.get(Message, message_id)
    if msg is None or msg.team_id != team_id:
        raise HTTPException(status_code=404, detail="消息不存在")
    if msg.sender_id != actor.id:
        raise HTTPException(status_code=403, detail="只能撤回自己发送的消息")
    if msg.msg_type == "system":
        raise HTTPException(status_code=409, detail="系统消息不可撤回")
    if msg.recalled_at is not None:
        return {"id": msg.id, "recalled": True}
    if now() - msg.created_at > timedelta(minutes=RECALL_WINDOW_MINUTES):
        raise HTTPException(
            status_code=409,
            detail=f"超过 {RECALL_WINDOW_MINUTES} 分钟的消息不可撤回",
        )

    msg.recalled_at = now()
    out = _out(db, msg, actor)
    enqueue(db, [{
        "kind": "broadcast",
        "payload": {
            "channel": f"team:{team_id}", "event": "chat.message",
            "data": {"team_id": team_id, "message": out, "recalled": True},
        },
    }])
    audit(db, actor.id, "chat.recall", "message", msg.id, team_id=team_id)
    db.commit()
    return out
