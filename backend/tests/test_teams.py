"""M2 验收：组队 CRUD / 发布守卫 / 广场"""

import datetime

from tests.conftest import API, create_team, make_restaurant, make_verified_user, publish_team, register


def test_create_draft_and_detail(client):
    headers, uid = make_verified_user(client, "leader1")
    team_id = create_team(client, headers, name="周五火锅", target_size=3, cuisine="火锅")
    r = client.get(f"{API}/teams/{team_id}", headers=headers)
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "draft"
    assert d["my_role"] == "leader"
    assert d["current_size"] == 1
    assert len(d["members"]) == 1
    assert d["members"][0]["role"] == "leader"


def test_publish_missing_fields_422(client):
    headers, _ = make_verified_user(client, "leader2")
    # 缺 target_size / cuisine / dining_time
    r = client.post(f"{API}/teams", json={"name": "残缺队伍", "mode": "invite"}, headers=headers)
    assert r.status_code == 200
    team_id = r.json()["id"]
    r2 = client.post(f"{API}/teams/{team_id}/publish", headers=headers)
    assert r2.status_code == 422


def test_publish_past_time_422(client):
    headers, _ = make_verified_user(client, "leader3")
    r = client.post(f"{API}/teams", json={
        "name": "过期局", "mode": "invite", "target_size": 3, "cuisine_type": "火锅",
        "dining_time": (datetime.datetime.now() - datetime.timedelta(days=1)).isoformat(),
    }, headers=headers)
    team_id = r.json()["id"]
    assert client.post(f"{API}/teams/{team_id}/publish", headers=headers).status_code == 422


def test_publish_ok_and_plaza_visible(client):
    headers, _ = make_verified_user(client, "leader4")
    team_id = create_team(client, headers, name="烤肉局", target_size=4, cuisine="烤肉")
    out = publish_team(client, headers, team_id)
    assert out["status"] == "recruiting"
    assert out["code"]  # invite 模式生成邀请码

    r = client.get(f"{API}/plaza/teams", headers=headers)
    assert r.status_code == 200
    ids = [t["id"] for t in r.json()["teams"]]
    assert team_id in ids
    card = next(t for t in r.json()["teams"] if t["id"] == team_id)
    assert card["remaining"] == 3
    assert card["profile"]["count"] == 1


def test_draft_not_in_plaza(client):
    headers, _ = make_verified_user(client, "leader5")
    team_id = create_team(client, headers)
    r = client.get(f"{API}/plaza/teams", headers=headers)
    assert team_id not in [t["id"] for t in r.json()["teams"]]


def test_only_leader_can_publish(client):
    headers, _ = make_verified_user(client, "leader6")
    other, _ = make_verified_user(client, "leader6b")
    team_id = create_team(client, headers)
    r = client.post(f"{API}/teams/{team_id}/publish", headers=other)
    assert r.status_code == 403


def test_anonymous_mode_no_code(client):
    headers, _ = make_verified_user(client, "leader7")
    team_id = create_team(client, headers, mode="anonymous")
    out = publish_team(client, headers, team_id)
    assert out["code"] is None


def test_update_draft(client):
    headers, _ = make_verified_user(client, "leader8")
    team_id = create_team(client, headers, target_size=3)
    r = client.patch(f"{API}/teams/{team_id}", json={"target_size": 5, "cuisine_type": "日料"}, headers=headers)
    assert r.status_code == 200
    d = client.get(f"{API}/teams/{team_id}", headers=headers).json()
    assert d["target_size"] == 5
    assert d["cuisine_type"] == "日料"


# ---------- M7：餐馆必填 + 预选菜品快照 ----------

def test_publish_without_restaurant_422(client):
    """餐馆为发布必填项"""
    headers, _ = make_verified_user(client, "leader9")
    r = client.post(f"{API}/teams", json={
        "name": "没选餐馆", "mode": "invite", "target_size": 3, "cuisine_type": "火锅",
        "dining_time": (datetime.datetime.now() + datetime.timedelta(days=1)).isoformat(),
    }, headers=headers)
    team_id = r.json()["id"]
    r2 = client.post(f"{API}/teams/{team_id}/publish", headers=headers)
    assert r2.status_code == 422
    assert "餐馆" in r2.json()["detail"]


def test_team_detail_restaurant_dishes_and_estimate(client):
    """选餐馆 + 选菜 → 详情回餐馆信息、菜品快照与预估消费"""
    headers, _ = make_verified_user(client, "leader10")
    rid, dish_ids = make_restaurant(client, name="蜀九香老灶火锅", cuisine="火锅",
                                    district="国贸商圈", avg_price=118, dish_count=3)
    team_id = create_team(client, headers, target_size=4, cuisine="火锅",
                          restaurant_id=rid, dish_ids=dish_ids[:2])
    d = client.get(f"{API}/teams/{team_id}", headers=headers).json()

    assert d["restaurant"]["id"] == rid
    assert d["restaurant"]["name"] == "蜀九香老灶火锅"
    assert d["restaurant"]["image"].startswith("/static/food/")
    assert len(d["dishes"]) == 2
    assert d["dishes"][0]["dish_id"] == dish_ids[0]
    assert set(d["dishes"][0].keys()) == {"dish_id", "name", "price", "image"}

    # 预估：30 + 40 = 70，按满员 4 人摊 → 17.50
    assert d["estimate"]["total"] == 70.0
    assert d["estimate"]["per_capita"] == 17.5
    assert d["estimate"]["dish_count"] == 2


def test_menu_snapshot_immutable_after_price_change(client):
    """菜品改价后，已发布队伍的快照价格不变"""
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models.dish import Dish

    headers, _ = make_verified_user(client, "leader11")
    rid, dish_ids = make_restaurant(client, name="快照餐馆", cuisine="烤肉", dish_count=1)
    team_id = create_team(client, headers, restaurant_id=rid, dish_ids=dish_ids)
    before = client.get(f"{API}/teams/{team_id}", headers=headers).json()
    assert before["dishes"][0]["price"] == 30.0

    db = SessionLocal()
    try:
        dish = db.execute(select(Dish).where(Dish.id == dish_ids[0])).scalar_one()
        dish.price = 99
        db.commit()
    finally:
        db.close()

    after = client.get(f"{API}/teams/{team_id}", headers=headers).json()
    assert after["dishes"][0]["price"] == 30.0  # 快照不随菜品改价变化
    assert after["estimate"]["total"] == 30.0


def test_update_draft_dish_ids_overwrites_snapshot(client):
    """草稿改选菜品 → 快照被覆盖；换餐馆不带菜品 → 清空旧快照"""
    headers, _ = make_verified_user(client, "leader12")
    rid1, dish_ids1 = make_restaurant(client, name="餐馆甲", cuisine="火锅", dish_count=3)
    rid2, _ = make_restaurant(client, name="餐馆乙", cuisine="粤菜", dish_count=2)

    team_id = create_team(client, headers, restaurant_id=rid1, dish_ids=dish_ids1[:3])
    d = client.get(f"{API}/teams/{team_id}", headers=headers).json()
    assert len(d["dishes"]) == 3

    # 改选 1 道
    r = client.patch(f"{API}/teams/{team_id}", json={"dish_ids": [dish_ids1[1]]}, headers=headers)
    assert r.status_code == 200
    d2 = client.get(f"{API}/teams/{team_id}", headers=headers).json()
    assert len(d2["dishes"]) == 1
    assert d2["dishes"][0]["dish_id"] == dish_ids1[1]

    # 换餐馆且不带菜品 → 清空
    r2 = client.patch(f"{API}/teams/{team_id}", json={"restaurant_id": rid2}, headers=headers)
    assert r2.status_code == 200
    d3 = client.get(f"{API}/teams/{team_id}", headers=headers).json()
    assert d3["restaurant"]["id"] == rid2
    assert d3["dishes"] == []
    assert d3["estimate"]["total"] == 0.0


def test_dish_from_other_restaurant_rejected(client):
    """菜品必须存在且有效，前端传脏 id 返回 422"""
    headers, _ = make_verified_user(client, "leader13")
    rid, _ = make_restaurant(client, name="餐馆丙", cuisine="素食")
    r = client.post(f"{API}/teams", json={
        "name": "脏菜品", "mode": "invite", "target_size": 3, "cuisine_type": "素食",
        "restaurant_id": rid, "dish_ids": [999999],
        "dining_time": (datetime.datetime.now() + datetime.timedelta(days=1)).isoformat(),
    }, headers=headers)
    assert r.status_code == 422


def test_recreate_keeps_restaurant(client):
    """解散重开必须带上餐馆，否则新草稿无法发布"""
    headers, _ = make_verified_user(client, "leader14")
    m1, _ = make_verified_user(client, "leader14m")
    rid, dish_ids = make_restaurant(client, name="重开餐馆", cuisine="日料", dish_count=2)
    team_id = create_team(client, headers, target_size=2, cuisine="日料",
                          restaurant_id=rid, dish_ids=dish_ids)
    publish_team(client, headers, team_id)
    client.post(f"{API}/teams/{team_id}/join", headers=m1)  # 满员成团

    assert client.post(f"{API}/teams/{team_id}/abort", headers=headers).status_code == 200
    new_id = client.post(f"{API}/teams/{team_id}/recreate", headers=headers).json()["id"]

    d = client.get(f"{API}/teams/{new_id}", headers=headers).json()
    assert d["restaurant"]["id"] == rid
    assert len(d["dishes"]) == 2
    # 新草稿可正常发布（餐馆已复制）
    assert publish_team(client, headers, new_id)["status"] == "recruiting"
