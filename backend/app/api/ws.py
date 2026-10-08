"""WebSocket 连接管理器 + /ws 端点。

频道模型：
- team:{id}  仅队伍活跃成员可订阅（组队/成团/聊天/核销/账单/支付实时事件）
- user:{id}  仅本人（个人通知）
- plaza      任何已实名用户（广场卡片刷新）
"""

import asyncio
import json
from collections import defaultdict

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.agent.states import MemberStatus
from app.core.deps import get_ws_user
from app.models.member import TeamMember
from app.services.common import active_member

router = APIRouter()


class ConnectionManager:
    def __init__(self):
        self.conns: dict[WebSocket, int] = {}  # ws -> user_id
        self.channels: dict[str, set[WebSocket]] = defaultdict(set)

    def connect(self, ws: WebSocket, user_id: int):
        self.conns[ws] = user_id

    def disconnect(self, ws: WebSocket):
        self.conns.pop(ws, None)
        for members in self.channels.values():
            members.discard(ws)

    def subscribe(self, ws: WebSocket, channels: list[str]) -> list[str]:
        """校验并订阅，返回成功订阅的频道"""
        user_id = self.conns.get(ws)
        ok = []
        for ch in channels:
            if self._can_subscribe(user_id, ch):
                self.channels[ch].add(ws)
                ok.append(ch)
        return ok

    def unsubscribe_user(self, channel: str, user_id: int) -> int:
        """把某用户从指定频道摘除，返回摘除的连接数。

        频道订阅只在 subscribe 时刻校验成员身份；踢人/退队后若不主动断订，
        存活连接（有心跳保活，可能很久）会继续收到该队 chat.message /
        bill.updated 等事件——这是信息泄漏窗口。由 worker 消费
        kick_channel 任务调用（与 broadcast 同在事件循环，无并发问题）。
        仅摘队伍频道：个人频道（user:{id}）的"你被移出了队伍"通知仍要送达。
        """
        members = self.channels.get(channel)
        if not members:
            return 0
        dead = [ws for ws, uid in self.conns.items() if uid == user_id and ws in members]
        for ws in dead:
            members.discard(ws)
        return len(dead)

    def _can_subscribe(self, user_id: int | None, channel: str) -> bool:
        if user_id is None:
            return False
        if channel == "plaza":
            return True
        if channel.startswith("user:"):
            return channel == f"user:{user_id}"
        if channel.startswith("team:"):
            try:
                team_id = int(channel.split(":", 1)[1])
            except ValueError:
                return False
            from app.db import SessionLocal

            db = SessionLocal()
            try:
                return active_member(db, team_id, user_id) is not None
            finally:
                db.close()
        return False

    async def broadcast(self, channel: str, event: str, data: dict):
        """向频道内所有连接推送（worker 在事件循环内调用）"""
        text = json.dumps({"event": event, "channel": channel, "data": data}, ensure_ascii=False)
        dead = []
        for ws in list(self.channels.get(channel, ())):
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def broadcast_many(self, tasks: list[dict]):
        for t in tasks:
            p = t.get("payload", {})
            await self.broadcast(p.get("channel", ""), p.get("event", ""), p.get("data", {}))


manager = ConnectionManager()

AUTH_TIMEOUT_SECONDS = 5.0


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket, token: str = Query("")):
    """WebSocket 鉴权。

    优先使用**首帧鉴权**（{"action":"auth","token":"..."}）：token 不再出现在 URL 里，
    避免写进服务器/网关访问日志。为兼容旧客户端仍接受 query 参数 token，
    但客户端应尽快迁移（前端 ws.js 已改为首帧鉴权）。
    """
    await ws.accept()

    user = None
    if token:
        user, _ = get_ws_user(token)
    if user is None:
        try:
            raw = await asyncio.wait_for(ws.receive_text(), timeout=AUTH_TIMEOUT_SECONDS)
        except (asyncio.TimeoutError, WebSocketDisconnect):
            await ws.close(code=4401)
            return
        try:
            msg = json.loads(raw)
        except Exception:
            await ws.close(code=4401)
            return
        if msg.get("action") != "auth":
            await ws.close(code=4401)
            return
        user, _ = get_ws_user(msg.get("token") or "")
    if user is None:
        await ws.close(code=4401)
        return

    manager.connect(ws, user.id)
    try:
        await ws.send_text(json.dumps({"event": "connected", "data": {"user_id": user.id}}))
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            action = msg.get("action")
            if action == "subscribe":
                ok = manager.subscribe(ws, list(msg.get("channels", [])))
                await ws.send_text(json.dumps({"event": "subscribed", "data": {"channels": ok}}))
            elif action == "ping":
                await ws.send_text(json.dumps({"event": "pong"}))
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(ws)
