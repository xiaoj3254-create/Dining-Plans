"""M4 验收：WebSocket 频道订阅 + 实时事件推送"""

import json
import time

import pytest

from tests.conftest import API, create_team, full_flow_formed, make_verified_user, publish_team, register


def _token_of(client, username):
    """已注册用户通过登录取 token（避免重复注册 409）"""
    r = client.post(f"{API}/auth/login", json={"username": username, "password": "pass123456"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_ws_subscribe_team_channel_and_events(client):
    leader, _ = make_verified_user(client, "wsleader")
    m1, _ = make_verified_user(client, "wsm1")
    team_id = create_team(client, leader, target_size=2)
    publish_team(client, leader, team_id)

    leader_token = client.post(f"{API}/auth/login", json={"username": "wsleader", "password": "pass123456"}).json()["access_token"]

    with client.websocket_connect(f"/ws?token={leader_token}") as ws:
        hello = json.loads(ws.receive_text())
        assert hello["event"] == "connected"

        ws.send_text(json.dumps({"action": "subscribe", "channels": [f"team:{team_id}"]}))
        sub = json.loads(ws.receive_text())
        assert sub["event"] == "subscribed"
        assert f"team:{team_id}" in sub["data"]["channels"]

        # 成员加入 → REST 写库 + worker 广播 → WS 收到事件
        client.post(f"{API}/teams/{team_id}/join", headers=m1)
        # 可能先收到 plaza.changed 或 team.member_joined，逐条读直到 member_joined
        got = None
        for _ in range(10):
            evt = json.loads(ws.receive_text())
            if evt["event"] == "team.member_joined":
                got = evt
                break
        assert got is not None
        assert got["data"]["member"]["nickname"] == "wsm1"
        assert got["data"]["current_size"] == 2


def test_ws_forbidden_channel_rejected(client):
    leader, _ = make_verified_user(client, "wsl2")
    m1, _ = make_verified_user(client, "wsm2")
    team_id = create_team(client, leader, target_size=3)
    publish_team(client, leader, team_id)  # m1 未加入

    token = _token_of(client, "wsm2")
    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_text()  # connected
        ws.send_text(json.dumps({"action": "subscribe", "channels": [f"team:{team_id}"]}))
        sub = json.loads(ws.receive_text())
        assert sub["data"]["channels"] == []  # 非成员订阅被拒


def test_ws_invalid_token_closed(client):
    with pytest.raises(Exception):
        with client.websocket_connect("/ws?token=invalid.token.here") as ws:
            ws.receive_text()


def test_ws_chat_broadcast(client):
    leader, _ = make_verified_user(client, "wsl3")
    m1, _ = make_verified_user(client, "wsm3")
    team_id = create_team(client, leader, target_size=2)
    full_flow_formed(client, leader, [m1], team_id)

    token = _token_of(client, "wsm3")
    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_text()  # connected
        ws.send_text(json.dumps({"action": "subscribe", "channels": [f"team:{team_id}"]}))
        json.loads(ws.receive_text())  # subscribed

        r = client.post(f"{API}/teams/{team_id}/messages",
                        json={"content": "大家好，6点准时到"}, headers=leader)
        assert r.status_code == 200

        for _ in range(10):
            evt = json.loads(ws.receive_text())
            if evt["event"] == "chat.message":
                assert evt["data"]["message"]["content"] == "大家好，6点准时到"
                assert evt["data"]["message"]["sender"]["nickname"] == "wsl3"
                return
        pytest.fail("未收到 chat.message 广播")


def test_team_detail_exposes_user_id_to_members_only(client):
    """回归：detail 成员项对**同队成员**暴露 user_id（踢人/举报/拉黑必需），对外部不暴露。

    设计变更说明：原实现只对队长暴露。但"只有队长能举报队长"是荒谬的——
    举报/拉黑的主体恰恰可能是普通队员，因此改为对全部活跃成员开放。
    纯数字 id 不属个人信息，平台也没有公开用户主页端点。
    """
    leader, _ = make_verified_user(client, "kzlead")
    m1, _ = make_verified_user(client, "kzm1")
    outsider, _ = make_verified_user(client, "kzout")
    team_id = create_team(client, leader, target_size=3)
    publish_team(client, leader, team_id)
    client.post(f"{API}/teams/{team_id}/join", headers=m1)

    d_leader = client.get(f"{API}/teams/{team_id}", headers=leader).json()
    assert all("user_id" in m for m in d_leader["members"])

    # 队员视角：同队成员互相可见（用于举报/拉黑）
    d_member = client.get(f"{API}/teams/{team_id}", headers=m1).json()
    assert all("user_id" in m for m in d_member["members"])

    # 非成员（招募态可看概况）拿不到名单，自然也没有 user_id
    d_out = client.get(f"{API}/teams/{team_id}", headers=outsider).json()
    assert d_out["members"] == []

    # 队长用 detail 返回的 user_id 完成踢人（此前前端拿不到该字段 → 踢人不可用）
    target = next(m for m in d_leader["members"] if m["role"] != "leader")
    r = client.post(f"{API}/teams/{team_id}/members/{target['user_id']}/kick", headers=leader)
    assert r.status_code == 200
    assert r.json()["current_size"] == 1


def test_notification_delete(client):
    """左滑删除：仅能删除本人通知，删除后列表不再返回"""
    leader, _ = make_verified_user(client, "ndlead")
    m1, _ = make_verified_user(client, "ndm1")
    team_id = create_team(client, leader, target_size=2)
    full_flow_formed(client, leader, [m1], team_id)  # 成团 → 双方收到 formed 通知

    items = client.get(f"{API}/notifications", headers=m1).json()["items"]
    assert items, "成团后应有站内通知"
    nid = items[0]["id"]

    # 他人（队长）不能删除我的通知
    assert client.delete(f"{API}/notifications/{nid}", headers=leader).status_code == 404

    assert client.delete(f"{API}/notifications/{nid}", headers=m1).status_code == 200
    after = client.get(f"{API}/notifications", headers=m1).json()["items"]
    assert all(n["id"] != nid for n in after)


# ---------- 复审回归（2026-10-08 第二轮审查）：踢人/退队即时断订 ----------

def _ws_login(client, username):
    return client.post(f"{API}/auth/login",
                       json={"username": username, "password": "pass123456"}).json()["access_token"]


def _wait_unsubscribed(channel, expect_left, timeout=4.0):
    """轮询等待 worker 消费 kick_channel 任务把频道连接数降到预期。"""
    from app.api.ws import manager

    deadline = time.time() + timeout
    while time.time() < deadline:
        if len(manager.channels.get(channel, ())) <= expect_left:
            return True
        time.sleep(0.05)
    return False


def test_ws_leave_unsubscribes_team_channel(client):
    """复审 P2-1：成团后退队，退队者的存活 WS 连接应立即从队伍频道摘除。"""
    from app.api.ws import manager

    leader, _ = make_verified_user(client, "unsub_L")
    m1, _ = make_verified_user(client, "unsub_M")
    m2, _ = make_verified_user(client, "unsub_N")
    team_id = create_team(client, leader, target_size=3, name="断订退队")
    full_flow_formed(client, leader, [m1, m2], team_id)
    ch = f"team:{team_id}"

    with client.websocket_connect(f"/ws?token={_ws_login(client, 'unsub_L')}") as wsl, \
         client.websocket_connect(f"/ws?token={_ws_login(client, 'unsub_M')}") as wsm:
        for w in (wsl, wsm):
            w.receive_text()  # connected
            w.send_text(json.dumps({"action": "subscribe", "channels": [ch]}))
            json.loads(w.receive_text())  # subscribed
        assert len(manager.channels[ch]) == 2

        # m1 退队（REST）→ kick_channel 任务入队 → worker 摘除其连接
        assert client.post(f"{API}/teams/{team_id}/leave", headers=m1).status_code == 200
        assert _wait_unsubscribed(ch, expect_left=1), "退队后连接未从队伍频道摘除"
        assert len(manager.channels[ch]) == 1  # 只剩队长

        # 摘除后队伍事件不再发给退队者，但队长仍正常接收
        r = client.post(f"{API}/teams/{team_id}/messages",
                        json={"content": "还有谁没到？"}, headers=leader)
        assert r.status_code == 200
        got = None
        for _ in range(10):
            evt = json.loads(wsl.receive_text())
            if evt["event"] == "chat.message":
                got = evt
                break
        assert got is not None  # 队长照常收到


def test_ws_kick_unsubscribes_team_channel(client):
    """复审 P2-1：被踢成员的存活 WS 连接应立即从队伍频道摘除（防泄漏窗口）。

    注意：KICK 仅存在于招募态流转表（成团后禁止踢人，只能等其自行退出）。
    """
    from app.api.ws import manager

    leader, _ = make_verified_user(client, "unsub_KL")
    m1, m1_id = make_verified_user(client, "unsub_KM")
    m2, _ = make_verified_user(client, "unsub_KN")
    m3, _ = make_verified_user(client, "unsub_K3")
    team_id = create_team(client, leader, target_size=4, name="断订踢人")
    publish_team(client, leader, team_id)
    client.post(f"{API}/teams/{team_id}/join", headers=m1)
    client.post(f"{API}/teams/{team_id}/join", headers=m2)
    ch = f"team:{team_id}"

    with client.websocket_connect(f"/ws?token={_ws_login(client, 'unsub_KL')}") as wsl, \
         client.websocket_connect(f"/ws?token={_ws_login(client, 'unsub_KM')}") as wsm:
        for w in (wsl, wsm):
            w.receive_text()  # connected
            w.send_text(json.dumps({"action": "subscribe", "channels": [ch]}))
            json.loads(w.receive_text())  # subscribed
        assert len(manager.channels[ch]) == 2

        # 队长踢出 m1（其连接已订阅队伍频道且保持存活）
        r = client.post(f"{API}/teams/{team_id}/members/{m1_id}/kick", headers=leader)
        assert r.status_code == 200
        assert _wait_unsubscribed(ch, expect_left=1), "被踢后连接未从队伍频道摘除"
        assert len(manager.channels[ch]) == 1  # 只剩队长

        # 被踢者用同一连接尝试重新订阅 → 成员身份已失，被拒
        # （先要排空踢人瞬间仍在途的 member_left 广播，再等 subscribed 响应）
        wsm.send_text(json.dumps({"action": "subscribe", "channels": [ch]}))
        for _ in range(10):
            msg = json.loads(wsm.receive_text())
            if msg.get("event") == "subscribed":
                assert msg["data"]["channels"] == []
                break
        else:
            pytest.fail("未收到重新订阅的响应")

        # 之后队伍里发生的事件（m3 加入）只广播给队长，不再触达被踢者。
        # 注意连接上可能还积压着订阅前已入队、此刻才被 worker 消费的旧广播，
        # 因此按昵称精确匹配而不是取第一条 member_joined。
        client.post(f"{API}/teams/{team_id}/join", headers=m3)
        got = None
        for _ in range(20):
            evt = json.loads(wsl.receive_text())
            if (evt["event"] == "team.member_joined"
                    and evt["data"]["member"].get("nickname") == "unsub_K3"):
                got = evt
                break
        assert got is not None  # 队长照常收到 m3 的加入事件
