"""M5 验收：核销 → 账单生效 → 独立支付 → 归档；异常路径 ABORT/recreate"""

import pytest

from tests.conftest import API, create_team, full_flow_formed, make_verified_user, publish_team


def _formed(client, size=3):
    leader, leader_id = make_verified_user(client, "bleader")
    members = []
    for i in range(size - 1):
        h, uid = make_verified_user(client, f"bm{i}")
        members.append((h, uid))
    team_id = create_team(client, leader, target_size=size)
    full_flow_formed(client, leader, [h for h, _ in members], team_id)
    return team_id, leader, leader_id, members


def _get_my_code(client, headers, team_id):
    return client.get(f"{API}/teams/{team_id}/checkins/me", headers=headers).json()["checkin_code"]


def test_checkin_requires_correct_code(client):
    team_id, leader, _, members = _formed(client)
    wrong = client.post(f"{API}/teams/{team_id}/checkin",
                        json={"checkin_code": "bad"}, headers=leader)
    assert wrong.status_code == 403
    right = client.post(f"{API}/teams/{team_id}/checkin",
                        json={"checkin_code": _get_my_code(client, leader, team_id)}, headers=leader)
    assert right.status_code == 200
    # 重复核销 409
    again = client.post(f"{API}/teams/{team_id}/checkin",
                        json={"checkin_code": _get_my_code(client, leader, team_id)}, headers=leader)
    assert again.status_code == 409


def test_bill_persists_until_all_checked(client):
    """部分核销时账单不锁定；全员核销 + 已录账单 → 自动生效"""
    team_id, leader, leader_id, members = _formed(client, size=3)
    # 队长先录账单
    r = client.post(f"{API}/teams/{team_id}/bill", json={"total_amount": "300"}, headers=leader)
    assert r.status_code == 200
    # 队长 + 第一名队员核销（2/3）
    for h in (leader, members[0][0]):
        client.post(f"{API}/teams/{team_id}/checkin",
                    json={"checkin_code": _get_my_code(client, h, team_id)}, headers=h)
    bill = client.get(f"{API}/teams/{team_id}/bill", headers=members[0][0]).json()
    assert bill["status"] == "pending"  # 未全员核销，不锁定
    # 最后一人核销 → 全员完成 → 自动锁定
    h2, u2 = members[1]
    client.post(f"{API}/teams/{team_id}/checkin", json={"checkin_code": _get_my_code(client, h2, team_id)}, headers=h2)
    bill2 = client.get(f"{API}/teams/{team_id}/bill", headers=leader).json()
    assert bill2["status"] == "locked"
    assert bill2["per_capita"] == 100.0
    assert bill2["total_members"] == 3
    # 队长补差：300 - 100*2 = 100（整除时相等）
    leader_pay = next(p for p in bill2["payments"] if p["user"]["nickname"] == "bleader")
    assert leader_pay["amount"] == 100.0


def test_bill_lock_deferred_until_submitted(client):
    """先全员核销、后录账单 → 录入时补触发锁定"""
    team_id, leader, leader_id, members = _formed(client, size=2)
    h1, u1 = members[0]
    for h in [leader, h1]:
        client.post(f"{API}/teams/{team_id}/checkin",
                    json={"checkin_code": _get_my_code(client, h, team_id)}, headers=h)
    r = client.post(f"{API}/teams/{team_id}/bill", json={"total_amount": "99.99"}, headers=leader)
    assert r.status_code == 200
    bill = client.get(f"{API}/teams/{team_id}/bill", headers=leader).json()
    assert bill["status"] == "locked"
    assert bill["per_capita"] == 50.0  # 99.99/2 → 50.0 (HALF_UP)
    # 队长补差 49.99，队员 50.0，合计 99.99
    amounts = sorted(p["amount"] for p in bill["payments"])
    assert amounts == [49.99, 50.0]
    assert abs(sum(amounts) - 99.99) < 1e-9


def test_pay_and_auto_complete(client):
    team_id, leader, leader_id, members = _formed(client, size=3)
    client.post(f"{API}/teams/{team_id}/bill", json={"total_amount": "300"}, headers=leader)
    for h in [leader] + [h for h, _ in members]:
        client.post(f"{API}/teams/{team_id}/checkin",
                    json={"checkin_code": _get_my_code(client, h, team_id)}, headers=h)

    # 账单生效前不可支付（此处已生效）。逐人独立支付：
    pay1 = client.post(f"{API}/teams/{team_id}/bill/pay", headers=members[0][0])
    assert pay1.status_code == 200
    bill = client.get(f"{API}/teams/{team_id}/bill", headers=leader).json()
    assert bill["status"] == "locked"  # 未全付清仍 locked
    assert bill["paid_count"] == 1

    # 未支付者重复支付语义：再次调用返回 409
    # 支付剩余两人
    client.post(f"{API}/teams/{team_id}/bill/pay", headers=members[1][0])
    r = client.post(f"{API}/teams/{team_id}/bill/pay", headers=leader)
    assert r.status_code == 200
    bill2 = client.get(f"{API}/teams/{team_id}/bill", headers=leader).json()
    assert bill2["status"] == "settled"
    assert bill2["paid_count"] == 3

    # 归档后队伍 completed，不可再操作
    d = client.get(f"{API}/teams/{team_id}", headers=leader).json()
    assert d["status"] == "completed"
    assert client.post(f"{API}/teams/{team_id}/checkin",
                       json={"checkin_code": "x"}, headers=leader).status_code in (403, 409)


def test_abort_and_recreate(client):
    team_id, leader, leader_id, members = _formed(client, size=3)
    client.post(f"{API}/teams/{team_id}/bill", json={"total_amount": "300"}, headers=leader)
    # 仅队长可 ABORT
    assert client.post(f"{API}/teams/{team_id}/abort", headers=members[0][0]).status_code == 403
    r = client.post(f"{API}/teams/{team_id}/abort", headers=leader)
    assert r.status_code == 200
    assert r.json()["status"] == "failed"
    # 账单作废
    bill = client.get(f"{API}/teams/{team_id}/bill", headers=leader).json()
    assert bill["status"] == "void"
    # 复制重开
    r2 = client.post(f"{API}/teams/{team_id}/recreate", headers=leader)
    assert r2.status_code == 200
    new_id = r2.json()["id"]
    d = client.get(f"{API}/teams/{new_id}", headers=leader).json()
    assert d["status"] == "draft"
    assert d["target_size"] == 3
    assert d["current_size"] == 1


def test_abort_blocked_after_any_payment(client):
    """已有成员支付后禁止 ABORT（钱已动）"""
    team_id, leader, leader_id, members = _formed(client, size=2)
    client.post(f"{API}/teams/{team_id}/bill", json={"total_amount": "200"}, headers=leader)
    for h in [leader, members[0][0]]:
        client.post(f"{API}/teams/{team_id}/checkin",
                    json={"checkin_code": _get_my_code(client, h, team_id)}, headers=h)
    client.post(f"{API}/teams/{team_id}/bill/pay", headers=members[0][0])
    assert client.post(f"{API}/teams/{team_id}/abort", headers=leader).status_code == 409


def test_bill_locked_cannot_resubmit(client):
    """回归：账单 LOCKED 后队长二次提交金额 → 409（此前触发重复支付记录 → 500）"""
    team_id, leader, leader_id, members = _formed(client, size=2)
    h1, _ = members[0]
    # 先录账单，再全员核销 → 自动锁定
    client.post(f"{API}/teams/{team_id}/bill", json={"total_amount": "200"}, headers=leader)
    for h in [leader, h1]:
        client.post(f"{API}/teams/{team_id}/checkin",
                    json={"checkin_code": _get_my_code(client, h, team_id)}, headers=h)
    bill = client.get(f"{API}/teams/{team_id}/bill", headers=leader).json()
    assert bill["status"] == "locked"

    # 二次提交 → 409，账单与支付记录不受影响
    r = client.post(f"{API}/teams/{team_id}/bill", json={"total_amount": "150"}, headers=leader)
    assert r.status_code == 409
    bill2 = client.get(f"{API}/teams/{team_id}/bill", headers=leader).json()
    assert bill2["status"] == "locked"
    assert bill2["total_amount"] == 200.0
    assert bill2["total_members"] == 2  # 不产生重复支付记录

    # 锁定后支付流程不受影响
    assert client.post(f"{API}/teams/{team_id}/bill/pay", headers=leader).status_code == 200


def test_checkin_timeout_reminder_precise_and_idempotent(client):
    """回归：核销超时提醒去重按 JSON 精确匹配 team_id（此前子串 contains 会被 team_id=1x 误屏蔽）；
    且同一队只发一次"""
    import json as _json

    from app.db import SessionLocal
    from app.services import notify_service
    from sqlalchemy import select
    from app.models.notification import Notification

    leader, leader_id = make_verified_user(client, "rleader")
    m1, _ = make_verified_user(client, "rm1")
    team_id = create_team(client, leader, target_size=2)
    full_flow_formed(client, leader, [m1], team_id)

    db = SessionLocal()
    try:
        # 模拟时间流逝：把就餐时间改到 3 小时前（发布守卫要求未来时间，故成团后直改）
        from datetime import datetime, timedelta

        from app.models.team import Team

        team = db.get(Team, team_id)
        team.dining_time = datetime.now() - timedelta(hours=3)
        db.commit()

        # 伪造一条 team_id 为「team_id 拼接数」的历史提醒（旧实现子串误匹配源）
        decoy_payload = _json.dumps(
            {"team_id": int(f"{team_id}1"), "team_name": "诱饵队", "unchecked": 1},
            ensure_ascii=False,
        )
        db.add(Notification(user_id=leader_id, type=notify_service.effects.NOTIFY_CHECKIN_REMINDER,
                            payload=decoy_payload))
        db.commit()

        res1 = notify_service.scan_checkin_timeout(db, 2)
        assert res1["stage1"] == 1  # 旧实现此处为 0（被诱饵 payload 子串误屏蔽）

        res2 = notify_service.scan_checkin_timeout(db, 2)
        assert res2["stage1"] == 0  # 幂等：同一队只发一次

        rows = db.execute(
            select(Notification).where(Notification.user_id == leader_id)
        ).scalars().all()
        # 幂等判定走结构化 team_id 列（不再解析 payload 文本）
        real = [r for r in rows
                if r.type == notify_service.effects.NOTIFY_CHECKIN_REMINDER
                and r.team_id == team_id]
        assert len(real) == 1
    finally:
        db.close()
