"""状态机流转表穷举测试（M2/M3/M4/M5 关键规则）"""

import pytest

from tests.conftest import API, create_team, full_flow_formed, make_verified_user, publish_team


def _form_team(client, leader, members, size=None):
    team_id = create_team(client, leader, target_size=size or (1 + len(members)))
    return team_id, full_flow_formed(client, leader, members, team_id)


def test_join_updates_size_and_plaza(client):
    leader, _ = make_verified_user(client, "l1")
    m1, _ = make_verified_user(client, "m1")
    team_id = create_team(client, leader, target_size=3)
    publish_team(client, leader, team_id)
    r = client.post(f"{API}/teams/{team_id}/join", headers=m1)
    assert r.status_code == 200
    assert r.json()["current_size"] == 2
    card = next(t for t in client.get(f"{API}/plaza/teams", headers=leader).json()["teams"]
                if t["id"] == team_id)
    assert card["remaining"] == 1


def test_auto_form_on_full(client):
    leader, _ = make_verified_user(client, "l2")
    m1, _ = make_verified_user(client, "m2a")
    m2, _ = make_verified_user(client, "m2b")
    team_id = create_team(client, leader, target_size=3)
    publish_team(client, leader, team_id)
    client.post(f"{API}/teams/{team_id}/join", headers=m1)
    r = client.post(f"{API}/teams/{team_id}/join", headers=m2)  # 满员 → 自动成团
    assert r.status_code == 200
    assert r.json()["status"] == "formed"

    # 报名入口关闭
    m3, _ = make_verified_user(client, "m2c")
    r2 = client.post(f"{API}/teams/{team_id}/join", headers=m3)
    assert r2.status_code == 409

    # 成团后解散被禁止（流转 #16）
    r3 = client.post(f"{API}/teams/{team_id}/disband", headers=leader)
    assert r3.status_code == 409


def test_leader_cannot_leave(client):
    leader, _ = make_verified_user(client, "l3")
    team_id = create_team(client, leader, target_size=3)
    publish_team(client, leader, team_id)
    r = client.post(f"{API}/teams/{team_id}/leave", headers=leader)
    assert r.status_code == 403


def test_leave_and_rejoin_revive(client):
    leader, _ = make_verified_user(client, "l4")
    m1, _ = make_verified_user(client, "m4a")
    team_id = create_team(client, leader, target_size=3)
    publish_team(client, leader, team_id)
    client.post(f"{API}/teams/{team_id}/join", headers=m1)
    assert client.post(f"{API}/teams/{team_id}/leave", headers=m1).status_code == 200
    # 复活式重加入
    r = client.post(f"{API}/teams/{team_id}/join", headers=m1)
    assert r.status_code == 200
    assert r.json()["current_size"] == 2


def test_kick_flow(client):
    leader, leader_id = make_verified_user(client, "l5")
    m1, m1_id = make_verified_user(client, "m5a")
    team_id = create_team(client, leader, target_size=3)
    publish_team(client, leader, team_id)
    client.post(f"{API}/teams/{team_id}/join", headers=m1)

    # 非队长踢人 → 403
    r = client.post(f"{API}/teams/{team_id}/members/{leader_id}/kick", headers=m1)
    assert r.status_code == 403
    # 队长踢人 → 200
    r2 = client.post(f"{API}/teams/{team_id}/members/{m1_id}/kick", headers=leader)
    assert r2.status_code == 200
    assert r2.json()["current_size"] == 1
    # 被踢者进入本队冷却：不能原地重新报名（原实现的"允许重新排队"
    # 让队长的移出操作对恶意用户毫无约束力，见审查报告 B-7）
    r3 = client.post(f"{API}/teams/{team_id}/join", headers=m1)
    assert r3.status_code == 403
    assert "移出" in r3.json()["detail"]


def test_close_invite(client):
    leader, _ = make_verified_user(client, "l6")
    team_id = create_team(client, leader, mode="invite", target_size=3)
    out = publish_team(client, leader, team_id)
    code = out["code"]

    r = client.post(f"{API}/teams/{team_id}/invite/close", headers=leader)
    assert r.status_code == 200
    assert r.json()["invite_open"] is False

    # 关闭后链接报名被拒
    m1, _ = make_verified_user(client, "m6a")
    r2 = client.post(f"{API}/teams/join/{code}", headers=m1)
    assert r2.status_code == 403


def test_join_by_link(client):
    leader, _ = make_verified_user(client, "l7")
    team_id = create_team(client, leader, mode="invite", target_size=3)
    code = publish_team(client, leader, team_id)["code"]
    m1, _ = make_verified_user(client, "m7a")
    r = client.post(f"{API}/teams/join/{code}", headers=m1)
    assert r.status_code == 200
    assert r.json()["current_size"] == 2

    # 错误邀请码
    m2, _ = make_verified_user(client, "m7b")
    r2 = client.post(f"{API}/teams/join/badcode1", headers=m2)
    assert r2.status_code == 404


def test_anonymous_team_no_link_join(client):
    """匿名模式仅广场报名，无 code、无链接入口"""
    leader, _ = make_verified_user(client, "l8")
    team_id = create_team(client, leader, mode="anonymous", target_size=3)
    out = publish_team(client, leader, team_id)
    assert out["code"] is None
    m1, _ = make_verified_user(client, "m8a")
    r = client.post(f"{API}/teams/join/whatever", headers=m1)
    assert r.status_code == 404
    # 广场报名仍可用
    assert client.post(f"{API}/teams/{team_id}/join", headers=m1).status_code == 200


def test_disband_before_form(client):
    leader, _ = make_verified_user(client, "l9")
    team_id = create_team(client, leader, target_size=3)
    publish_team(client, leader, team_id)
    r = client.post(f"{API}/teams/{team_id}/disband", headers=leader)
    assert r.status_code == 200
    assert r.json()["status"] == "failed"
    # failed 不在广场
    ids = [t["id"] for t in client.get(f"{API}/plaza/teams", headers=leader).json()["teams"]]
    assert team_id not in ids


def test_non_member_cannot_see_formed_detail(client):
    leader, _ = make_verified_user(client, "l10")
    m1, _ = make_verified_user(client, "m10a")
    outsider, _ = make_verified_user(client, "m10b")
    team_id = create_team(client, leader, target_size=2)
    publish_team(client, leader, team_id)
    client.post(f"{API}/teams/{team_id}/join", headers=m1)  # 满员成团
    r = client.get(f"{API}/teams/{team_id}", headers=outsider)
    assert r.status_code == 403
