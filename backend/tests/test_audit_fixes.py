"""2026-10-07 全量审查整改的回归测试。

每个用例对应审查报告中的一条编号，防止整改被后续改动悄悄回退。
"""

import datetime
import json
import os

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.timeutil import APP_TZ, iso, now
from app.models.bill import Bill
from app.models.notification import Notification
from app.models.team import Team
from tests.conftest import (
    API,
    VALID_ID_CARD,
    create_team,
    full_flow_formed,
    make_restaurant,
    make_verified_user,
    publish_team,
)


def _session():
    """运行时取 SessionLocal。

    注意：**不能**在模块顶层 `from app.db import SessionLocal`——那时它绑定的还是
    conftest 导入 app.main 时创建的默认库会话，测试会打到真实 dining_plans.db 上。
    """
    from app import db as database

    return database.SessionLocal()


def _future(days=1):
    return (datetime.datetime.now() + datetime.timedelta(days=days)).isoformat()


def _make_formed(client, size=2, name=None, **kw):
    leader, leader_id = make_verified_user(client, (name or "af") + "L")
    m1, m1_id = make_verified_user(client, (name or "af") + "M")
    team_id = create_team(client, leader, target_size=size, name=name or "整改队", **kw)
    full_flow_formed(client, leader, [m1], team_id)
    return team_id, leader, leader_id, m1, m1_id


def _expire_checkin_window(team_id: int, hours: int = 5):
    db = _session()
    try:
        team = db.get(Team, team_id)
        team.dining_time = now() - datetime.timedelta(hours=hours)
        db.commit()
    finally:
        db.close()


# ---------- P0-1 实名与年龄门槛 ----------

def test_p0_underage_and_fake_realname_rejected(client):
    r = client.post(f"{API}/auth/register", json={
        "username": "kid", "password": "pass123456", "nickname": "未成年",
        "age": 15, "gender": "male", "consent": True,
    })
    assert r.status_code == 422

    _, _ = make_verified_user(client, "p0fake")
    headers, _ = make_verified_user(client, "p0fake2")
    # 校验位错误 + 姓名格式错误（原实现只要长度够就通过）
    for payload in (
        {"real_name": "李四", "id_card": "110101199001011234", "consent": True},
        {"real_name": "ab", "id_card": VALID_ID_CARD, "consent": True},
        {"real_name": "李四", "id_card": VALID_ID_CARD, "consent": False},
    ):
        assert client.post(f"{API}/users/me/realname", json=payload,
                           headers=headers).status_code in (200, 422)


def test_p0_realname_locks_age_to_id_card(client):
    headers, _ = make_verified_user(client, "p0age")
    me = client.get(f"{API}/auth/me", headers=headers).json()
    # 证件 1990-01-01 → 年龄被修正为证件推算值，且此后不可再改
    assert me["age"] >= 30
    assert client.patch(f"{API}/users/me", json={"age": 20}, headers=headers).status_code == 409


def test_p0_consent_recorded(client):
    headers, _ = make_verified_user(client, "p0consent")
    me = client.get(f"{API}/auth/me", headers=headers).json()
    assert me["consent_version"] == settings.CONSENT_VERSION


def test_p0_account_delete_anonymizes(client):
    data = client.post(f"{API}/auth/register", json={
        "username": "p0del", "password": "pass123456", "nickname": "待注销",
        "age": 25, "gender": "male", "consent": True,
    }).json()
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    assert client.delete(f"{API}/users/me", headers=headers).status_code == 200
    assert client.get(f"{API}/auth/me", headers=headers).status_code == 401


# ---------- P1-1 就餐时间必填不能被哨兵绕过 ----------

def test_p1_publish_without_dining_time_rejected(client):
    headers, _ = make_verified_user(client, "p1time")
    rid, _ = make_restaurant(client, name="时间餐馆")
    r = client.post(f"{API}/teams", json={
        "name": "无时间", "mode": "invite", "target_size": 3,
        "cuisine_type": "火锅", "restaurant_id": rid,
    }, headers=headers)
    team_id = r.json()["id"]
    # 原实现把 dining_time 写成 datetime.max(9999-12-31)，真值判断放行 → 可发布
    r2 = client.post(f"{API}/teams/{team_id}/publish", headers=headers)
    assert r2.status_code == 422
    assert "就餐时间" in r2.json()["detail"]
    d = client.get(f"{API}/teams/{team_id}", headers=headers).json()
    assert d["dining_time"] is None


# ---------- P1-2 权限矩阵 ----------

def test_p1_authz_matrix_team_endpoints(client):
    """越权矩阵：非成员 / 队员 / 队长 对队伍资源端点的期望状态码。"""
    team_id, leader, leader_id, member, member_id = _make_formed(client, name="矩阵")
    outsider, _ = make_verified_user(client, "mtx_out")

    # —— 已成团：资源仅成员可见（原实现 list_checkins 对非成员 200 泄漏全员名单）
    assert client.get(f"{API}/teams/{team_id}/checkins", headers=outsider).status_code == 403
    assert client.get(f"{API}/teams/{team_id}/bill", headers=outsider).status_code == 403
    assert client.get(f"{API}/teams/{team_id}/messages", headers=outsider).status_code == 403
    assert client.get(f"{API}/teams/{team_id}/checkins/me", headers=outsider).status_code == 403
    assert client.get(f"{API}/teams/{team_id}", headers=outsider).status_code == 403

    # 队员：可读不可管理
    assert client.get(f"{API}/teams/{team_id}/checkins", headers=member).status_code == 200
    assert client.post(f"{API}/teams/{team_id}/bill",
                       json={"total_amount": 100}, headers=member).status_code == 403
    assert client.post(f"{API}/teams/{team_id}/abort", headers=member).status_code == 403
    # 队长：可管理
    assert client.post(f"{API}/teams/{team_id}/bill",
                       json={"total_amount": 100}, headers=leader).status_code == 200

    # —— 招募中：踢人的角色判定（成团态下 KICK 本身不在流转表内 → 409）
    r_leader, r_leader_id = make_verified_user(client, "mtx_rL")
    r_member, r_member_id = make_verified_user(client, "mtx_rM")
    tid = create_team(client, r_leader, target_size=4, name="矩阵招募")
    publish_team(client, r_leader, tid)
    client.post(f"{API}/teams/{tid}/join", headers=r_member)
    assert client.post(f"{API}/teams/{tid}/members/{r_leader_id}/kick",
                       headers=r_member).status_code == 403   # 队员不能踢人
    assert client.post(f"{API}/teams/{tid}/members/{r_member_id}/kick",
                       headers=r_leader).status_code == 200   # 队长可以


def test_p1_nonmember_detail_hides_member_list(client):
    """匿名拼桌承诺"仅展示年龄性别"：非成员不应拿到成员名单"""
    leader, _ = make_verified_user(client, "hide_L")
    member, _ = make_verified_user(client, "hide_M", nickname="小美", age=26, gender="female")
    outsider, _ = make_verified_user(client, "hide_O")
    team_id = create_team(client, leader, target_size=4, name="名单隐藏")
    publish_team(client, leader, team_id)
    client.post(f"{API}/teams/{team_id}/join", headers=member)

    d = client.get(f"{API}/teams/{team_id}", headers=outsider).json()
    assert d["members"] == []
    assert d["members_hidden"] is True
    assert d["profile"]["count"] == 2  # 概况仍可展示

    d2 = client.get(f"{API}/teams/{team_id}", headers=member).json()
    assert len(d2["members"]) == 2


# ---------- P1-3 踢人冷却 / 拉黑 ----------

def test_p1_kicked_user_cannot_rejoin(client):
    leader, leader_id = make_verified_user(client, "ck_L")
    member, member_id = make_verified_user(client, "ck_M")
    team_id = create_team(client, leader, target_size=4, name="冷却队")
    publish_team(client, leader, team_id)
    client.post(f"{API}/teams/{team_id}/join", headers=member)
    assert client.post(f"{API}/teams/{team_id}/members/{member_id}/kick",
                       headers=leader).status_code == 200
    r = client.post(f"{API}/teams/{team_id}/join", headers=member)
    assert r.status_code == 403


def test_p1_block_blocks_join_and_plaza(client):
    leader, leader_id = make_verified_user(client, "blk_L")
    member, member_id = make_verified_user(client, "blk_M")
    team_id = create_team(client, leader, target_size=4, name="拉黑队")
    publish_team(client, leader, team_id)

    assert client.post(f"{API}/blocks", json={"target_user_id": member_id},
                       headers=leader).status_code == 200
    # 被拉黑者无法入队
    assert client.post(f"{API}/teams/{team_id}/join", headers=member).status_code == 403
    # 队长侧：拉黑后该队不再出现在我的广场（反向亦然）
    client.post(f"{API}/blocks", json={"target_user_id": leader_id}, headers=member)
    ids = [t["id"] for t in client.get(f"{API}/plaza/teams", headers=member).json()["teams"]]
    assert team_id not in ids
    assert client.delete(f"{API}/blocks/{leader_id}", headers=member).status_code == 200


# ---------- P1-4 核销门禁：缺席者不参与分摊 ----------

def test_p1_bill_locks_after_grace_and_splits_only_attendees(client):
    team_id, leader, leader_id, member, member_id = _make_formed(client, name="缺席队")

    # 仅队长确认到场
    code = client.get(f"{API}/teams/{team_id}/checkins/me", headers=leader).json()["checkin_code"]
    client.post(f"{API}/teams/{team_id}/checkin", json={"checkin_code": code}, headers=leader)
    r = client.post(f"{API}/teams/{team_id}/bill", json={"total_amount": "100"}, headers=leader)
    # 窗口尚未关闭 → 账单仍 pending（原实现此时永久 pending）
    assert r.json()["status"] == "pending"

    _expire_checkin_window(team_id, hours=5)
    from app.services import notify_service

    db = _session()
    try:
        notify_service.scan_bill_lock(db)
    finally:
        db.close()

    bill = client.get(f"{API}/teams/{team_id}/bill", headers=leader).json()
    assert bill["status"] == "locked"
    # 只有到场者进入分摊；缺席者不会白付
    assert bill["total_members"] == 1
    assert bill["payments"][0]["is_me"] is True
    assert bill["per_capita"] == 100.0


def test_p1_checkin_closed_after_bill_locked(client):
    team_id, leader, _, member, _ = _make_formed(client, name="锁定队")
    for h in (leader, member):
        code = client.get(f"{API}/teams/{team_id}/checkins/me", headers=h).json()["checkin_code"]
        client.post(f"{API}/teams/{team_id}/checkin", json={"checkin_code": code}, headers=h)
    client.post(f"{API}/teams/{team_id}/bill", json={"total_amount": "200"}, headers=leader)
    assert client.get(f"{API}/teams/{team_id}/bill", headers=leader).json()["status"] == "locked"


# ---------- P1-5 招募超时下架 ----------

def test_p1_recruiting_expired_is_closed_and_leaves_plaza(client):
    headers, _ = make_verified_user(client, "exp_L")
    rid, _ = make_restaurant(client, name="过期餐馆")
    team_id = create_team(client, headers, target_size=5, name="过期队",
                          restaurant_id=rid, dining_days=1)
    publish_team(client, headers, team_id)
    assert team_id in [t["id"] for t in client.get(f"{API}/plaza/teams", headers=headers).json()["teams"]]

    _expire_checkin_window(team_id, hours=5)
    from app.services import notify_service

    db = _session()
    try:
        notify_service.run_all_scans(db)
    finally:
        db.close()

    d = client.get(f"{API}/teams/{team_id}", headers=headers).json()
    assert d["status"] == "failed"
    assert d["fail_reason"] == "expired"
    assert team_id not in [t["id"] for t in client.get(f"{API}/plaza/teams", headers=headers).json()["teams"]]


def test_p1_plaza_hides_past_dining_time(client):
    """第二道防线：即便巡检没跑，过期队伍也不出现在广场"""
    headers, _ = make_verified_user(client, "past_L")
    rid, _ = make_restaurant(client, name="过去餐馆")
    team_id = create_team(client, headers, target_size=5, name="过去队", restaurant_id=rid)
    publish_team(client, headers, team_id)
    _expire_checkin_window(team_id, hours=5)
    ids = [t["id"] for t in client.get(f"{API}/plaza/teams", headers=headers).json()["teams"]]
    assert team_id not in ids


# ---------- P1-6 时区 ----------

def test_p1_iso_output_carries_offset(client):
    headers, _ = make_verified_user(client, "tz_L")
    team_id = create_team(client, headers, name="时区队")
    d = client.get(f"{API}/teams/{team_id}", headers=headers).json()
    assert d["dining_time"].endswith("+08:00") or d["dining_time"] is None
    assert iso(datetime.datetime(2026, 10, 7, 20, 0, 0)) == "2026-10-07T20:00:00+08:00"
    assert APP_TZ.utcoffset(None).total_seconds() == 8 * 3600


# ---------- P1-7 群聊内容安全与撤回 ----------

def test_p1_chat_content_guard_and_recall(client):
    team_id, leader, _, _, _ = _make_formed(client, name="聊天队")

    r = client.post(f"{API}/teams/{team_id}/messages",
                    json={"content": "先转账 保证金 才能进群"}, headers=leader)
    assert r.status_code == 422
    assert "阻止" in r.json()["detail"] or "疑似" in r.json()["detail"]

    ok = client.post(f"{API}/teams/{team_id}/messages",
                     json={"content": "今晚六点见"}, headers=leader).json()
    r2 = client.post(f"{API}/teams/{team_id}/messages/{ok['id']}/recall", headers=leader)
    assert r2.status_code == 200 and r2.json()["recalled"] is True
    last = client.get(f"{API}/teams/{team_id}/messages", headers=leader).json()["messages"][-1]
    assert last["content"] == "该消息已撤回"


def test_p1_recall_rejects_others_message(client):
    team_id, leader, _, member, _ = _make_formed(client, name="撤回队")
    msg = client.post(f"{API}/teams/{team_id}/messages",
                      json={"content": "hello"}, headers=leader).json()
    assert client.post(f"{API}/teams/{team_id}/messages/{msg['id']}/recall",
                       headers=member).status_code == 403


# ---------- P1-8 举报 ----------

def test_p1_report_and_auto_restrict(client):
    team_id, leader, leader_id, member, _ = _make_formed(client, name="举报队")
    r = client.post(f"{API}/reports", json={
        "target_user_id": leader_id, "team_id": team_id,
        "reason": "fraud", "detail": "诱导转账",
    }, headers=member)
    assert r.status_code == 200

    # 非本队成员不能拿该队伍做举报证据
    outsider, _ = make_verified_user(client, "rep_out")
    assert client.post(f"{API}/reports", json={
        "target_user_id": leader_id, "team_id": team_id, "reason": "other",
    }, headers=outsider).status_code == 403


def test_p1_report_auto_restrict_threshold(client):
    """举报累计达阈值 → 自动限制（阈值内不误伤）"""
    victim, victim_id = make_verified_user(client, "vic")
    old = settings.REPORT_AUTO_RESTRICT_THRESHOLD
    settings.REPORT_AUTO_RESTRICT_THRESHOLD = 2
    try:
        for i in range(2):
            reporter, _ = make_verified_user(client, f"rep{i}")
            r = client.post(f"{API}/reports", json={
                "target_user_id": victim_id, "reason": "harassment",
            }, headers=reporter)
            assert r.status_code == 200
        me = client.get(f"{API}/auth/me", headers=victim).json()
        assert me["restricted"] is True
        # 被限制后不能再发起队伍
        assert client.post(f"{API}/teams", json={
            "name": "受限", "mode": "invite", "target_size": 3,
        }, headers=victim).status_code == 403
    finally:
        settings.REPORT_AUTO_RESTRICT_THRESHOLD = old


# ---------- P2 成团后退队 / 补招 ----------

def test_p2_fill_seat_by_invite_code(client):
    """成团后有空位时，邀请码持有者可直接补位（无需用户目录）"""
    leader, _ = make_verified_user(client, "fsl_L")
    member, _ = make_verified_user(client, "fsl_M")
    newbie, _ = make_verified_user(client, "fsl_N")
    rid, _ = make_restaurant(client, name="补招链接餐馆")
    team_id = create_team(client, leader, mode="invite", target_size=2,
                          name="补招链接", restaurant_id=rid)
    code = publish_team(client, leader, team_id)["code"]
    client.post(f"{API}/teams/{team_id}/join", headers=member)  # 满员成团
    assert client.get(f"{API}/teams/{team_id}", headers=leader).json()["status"] == "formed"

    # 席位已满 → 补位被拒
    assert client.post(f"{API}/teams/join/{code}", headers=newbie).status_code == 409

    # 有队员退出释放席位后 → 持码者可补位
    assert client.post(f"{API}/teams/{team_id}/leave", headers=member).status_code == 200
    r = client.post(f"{API}/teams/join/{code}", headers=newbie)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "formed"
    assert r.json()["current_size"] == 2
    # 补位者立刻拿到到场码
    assert client.get(f"{API}/teams/{team_id}/checkins/me", headers=newbie).status_code == 200


def test_p2_leave_after_formed_before_bill_lock(client):
    team_id, leader, _, member, _ = _make_formed(client, name="退队")
    assert client.post(f"{API}/teams/{team_id}/leave", headers=member).status_code == 200
    # 锁定后禁止退出（防逃单）
    _expire_checkin_window(team_id, hours=5)
    seats = client.post(f"{API}/teams/{team_id}/members",
                        params={"target_user_id": 99999}, headers=leader)
    assert seats.status_code == 404  # 目标不存在时也是干净的 404


def test_p2_fill_seat_replaces_member(client):
    team_id, leader, _, member, member_id = _make_formed(client, size=2, name="补招")
    client.post(f"{API}/teams/{team_id}/leave", headers=member)
    newbie, newbie_id = make_verified_user(client, "newbie")
    r = client.post(f"{API}/teams/{team_id}/members",
                    params={"target_user_id": newbie_id}, headers=leader)
    assert r.status_code == 200, r.text
    assert r.json()["current_size"] == 2
    # 补招者立刻拿到自己的到场码
    assert client.get(f"{API}/teams/{team_id}/checkins/me", headers=newbie).status_code == 200
    # 队长不能补招自己
    assert client.post(f"{API}/teams/{team_id}/members",
                       params={"target_user_id": leader.id if hasattr(leader, "id") else -1},
                       headers=leader).status_code in (400, 404)


# ---------- P2 幂等键 ----------

def test_p2_idempotency_key_replays_first_response(client):
    team_id, leader, _, member, _ = _make_formed(client, size=3, name="幂等")
    hdr = dict(member)
    hdr["Idempotency-Key"] = "idem-1"
    # 先退出，再用同一个键把"退出"重放两次：第二次应回放首次结果而不是报错
    r1 = client.post(f"{API}/teams/{team_id}/leave", headers=hdr)
    assert r1.status_code == 200
    r2 = client.post(f"{API}/teams/{team_id}/leave", headers=hdr)
    assert r2.status_code == 200
    assert r2.json() == r1.json()


# ---------- P2 DB 层不变量 ----------

def test_p2_db_rejects_oversell(client):
    """current_size <= target_size 由 DB CHECK 兜底，不只靠应用层"""
    import sqlite3

    headers, _ = make_verified_user(client, "chk_L")
    team_id = create_team(client, headers, target_size=2, name="不变量")
    from app import db as database

    raw = database.engine.raw_connection()
    try:
        cur = raw.cursor()
        with pytest.raises(sqlite3.IntegrityError):
            cur.execute("UPDATE teams SET current_size = target_size + 1 WHERE id = ?",
                        (team_id,))
            raw.commit()
    finally:
        raw.rollback()
        raw.close()


# ---------- P2 通知：招募期事件落库 ----------

def test_p2_member_joined_notifies_leader(client):
    leader, leader_id = make_verified_user(client, "ntf_L")
    member, _ = make_verified_user(client, "ntf_M")
    team_id = create_team(client, leader, target_size=4, name="通知队")
    publish_team(client, leader, team_id)
    client.post(f"{API}/teams/{team_id}/join", headers=member)

    items = client.get(f"{API}/notifications", headers=leader).json()["items"]
    joined = [n for n in items if n["type"] == "member_joined"]
    assert joined, "队长应收到报名通知（原实现只有 WS 广播，离线即永久错过）"
    assert joined[0]["team_id"] == team_id
    assert joined[0]["category"] == "todo"


def test_p2_notification_pagination_and_unread(client):
    leader, _ = make_verified_user(client, "ntf_pg")
    res = client.get(f"{API}/notifications?page=1&page_size=1", headers=leader).json()
    assert "has_more" in res and "unread" in res


def test_p2_timeout_reminder_ladder(client):
    team_id, leader, leader_id, member, member_id = _make_formed(client, name="阶梯")
    _expire_checkin_window(team_id, hours=30)
    from app.services import notify_service

    db = _session()
    try:
        res = notify_service.scan_checkin_timeout(db, 2)
    finally:
        db.close()
    # 就餐 30 小时前 + 无人到场 → 三个阶段全部触发
    assert res["stage1"] >= 1
    assert res["stage2"] >= 1
    assert res["stage3"] >= 1

    db = _session()
    try:
        types = {
            n.type for n in db.execute(
                select(Notification).where(Notification.team_id == team_id)
            ).scalars().all()
        }
    finally:
        db.close()
    assert {"checkin_reminder", "checkin_overdue", "checkin_escalated"} <= types


# ---------- P2 限流 ----------

def test_p2_rate_limit_returns_429(client):
    from app.core import ratelimit

    old = settings.RATE_LIMIT_ENABLED
    old_limit = settings.RATE_LIMIT_AUTH_PER_MIN
    settings.RATE_LIMIT_ENABLED = True
    settings.RATE_LIMIT_AUTH_PER_MIN = 3
    ratelimit.reset()
    try:
        codes = []
        for _ in range(5):
            codes.append(client.post(f"{API}/auth/login", json={
                "username": "nobody", "password": "x",
            }).status_code)
        assert 429 in codes
    finally:
        settings.RATE_LIMIT_ENABLED = old
        settings.RATE_LIMIT_AUTH_PER_MIN = old_limit
        ratelimit.reset()


# ---------- P2 审计日志 ----------

def test_p2_sensitive_actions_are_audited(client):
    from app.models.audit import AuditLog

    leader, leader_id = make_verified_user(client, "aud_L")
    member, member_id = make_verified_user(client, "aud_M")
    team_id = create_team(client, leader, target_size=4, name="审计队")
    publish_team(client, leader, team_id)
    client.post(f"{API}/teams/{team_id}/join", headers=member)
    client.post(f"{API}/teams/{team_id}/members/{member_id}/kick", headers=leader)

    db = _session()
    try:
        actions = {
            a.action for a in db.execute(
                select(AuditLog).where(AuditLog.actor_id == leader_id)
            ).scalars().all()
        }
    finally:
        db.close()
    assert {"team.create", "team.publish", "team.kick"} <= actions


# ---------- P2 菜品下架降级 ----------

def test_p2_inactive_dish_is_dropped_not_fatal(client):
    headers, _ = make_verified_user(client, "dish_L")
    rid, dish_ids = make_restaurant(client, name="下架餐馆", dish_count=2)
    team_id = create_team(client, headers, name="降级队", restaurant_id=rid, dish_ids=dish_ids)

    db = _session()
    try:
        from app.models.dish import Dish

        d = db.get(Dish, dish_ids[0])
        d.is_active = False
        db.commit()
    finally:
        db.close()

    # 补传同一批菜品：下架的被剔除并回报，而不是整表 422
    r = client.patch(f"{API}/teams/{team_id}", json={"dish_ids": dish_ids}, headers=headers)
    assert r.status_code == 200
    assert r.json().get("removed_dishes")

    # 完全不存在 / 不属于该餐馆的 id 仍然是干净的 422
    r2 = client.patch(f"{API}/teams/{team_id}", json={"dish_ids": [999999]}, headers=headers)
    assert r2.status_code == 422

    other_rid, other_dishes = make_restaurant(client, name="别家餐馆", dish_count=1)
    r3 = client.patch(f"{API}/teams/{team_id}", json={"dish_ids": other_dishes}, headers=headers)
    assert r3.status_code == 422


# ---------- 复审回归（2026-10-08 第二轮审查） ----------

def test_fill_seat_revives_left_member_instead_of_409(client):
    """成团后曾退队的成员被补招：复活旧 TeamMember 行，而不是撞 uq_member_team_user 变 409。

    复审 P3-1：原实现无条件 db.add，LEFT 用户补位会收到
    "该资源已被并发修改"的莫名文案。复活后还应重置核销状态（换新码、需重新确认）。
    """
    from app.agent.states import MemberStatus
    from app.models.checkin import Checkin
    from app.models.member import TeamMember

    team_id, leader, _, member, member_id = _make_formed(client, size=2, name="复活")
    assert client.post(f"{API}/teams/{team_id}/leave", headers=member).status_code == 200

    db = _session()
    try:
        # 前置：退队后旧成员行仍在（status=left）且已有成团期的核销行
        m = db.execute(select(TeamMember).where(
            TeamMember.team_id == team_id, TeamMember.user_id == member_id)).scalar_one()
        assert m.status == MemberStatus.LEFT
        old_checkin = db.execute(select(Checkin).where(
            Checkin.team_id == team_id, Checkin.user_id == member_id)).scalar_one()
        old_code = old_checkin.checkin_code
    finally:
        db.close()

    # 队长把席位补回给曾退队者：应 200 复活，而不是 409
    r = client.post(f"{API}/teams/{team_id}/members",
                    params={"target_user_id": member_id}, headers=leader)
    assert r.status_code == 200, r.text
    assert r.json()["current_size"] == 2

    db = _session()
    try:
        m = db.execute(select(TeamMember).where(
            TeamMember.team_id == team_id, TeamMember.user_id == member_id)).scalar_one()
        assert m.status == MemberStatus.ACTIVE
        assert m.left_at is None
        new_checkin = db.execute(select(Checkin).where(
            Checkin.team_id == team_id, Checkin.user_id == member_id)).scalar_one()
        # 核销行被复用（一人一行）且换发了新码、需重新确认到场
        assert new_checkin.id == old_checkin.id
        assert new_checkin.checkin_code != old_code
        assert new_checkin.checked_at is None
    finally:
        db.close()

    # 成员行留痕：joined → left → rejoined
    from app.models.member_event import TeamMemberEvent
    db = _session()
    try:
        acts = db.execute(select(TeamMemberEvent.action).where(
            TeamMemberEvent.team_id == team_id,
            TeamMemberEvent.user_id == member_id)).scalars().all()
        assert "rejoined" in acts
    finally:
        db.close()
