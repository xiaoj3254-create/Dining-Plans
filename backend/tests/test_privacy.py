"""M6 验收：脱敏铁律 + 匿名模式约束 + 实名拦截"""

from tests.conftest import API, create_team, full_flow_formed, make_verified_user, publish_team, register

FORBIDDEN_KEYS = {"username", "password", "real_name", "id_card", "real_name_hash",
                  "id_card_hash", "phone", "mobile", "alipay_user_id"}


def _assert_no_forbidden(obj, path="root"):
    if isinstance(obj, dict):
        for k, v in obj.items():
            assert k not in FORBIDDEN_KEYS, f"脱敏违规：{path}.{k}"
            _assert_no_forbidden(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _assert_no_forbidden(v, f"{path}[{i}]")


def test_plaza_and_team_detail_desensitized(client):
    leader, _ = make_verified_user(client, "pleader")
    m1, _ = make_verified_user(client, "pm1", nickname="小王", age=30, gender="female")
    team_id = create_team(client, leader, target_size=2)
    publish_team(client, leader, team_id)
    client.post(f"{API}/teams/{team_id}/join", headers=m1)

    plaza = client.get(f"{API}/plaza/teams", headers=leader).json()
    _assert_no_forbidden(plaza, "plaza")

    detail = client.get(f"{API}/teams/{team_id}", headers=leader).json()
    _assert_no_forbidden(detail, "detail")
    assert set(detail["members"][0]["user"].keys()) == {"nickname", "age", "gender"}


def test_chat_and_checkin_desensitized(client):
    leader, _ = make_verified_user(client, "clead")
    m1, _ = make_verified_user(client, "cm1")
    team_id = create_team(client, leader, target_size=2)
    full_flow_formed(client, leader, [m1], team_id)

    client.post(f"{API}/teams/{team_id}/messages", json={"content": "hi"}, headers=leader)
    msgs = client.get(f"{API}/teams/{team_id}/messages", headers=m1).json()
    _assert_no_forbidden(msgs, "messages")

    checks = client.get(f"{API}/teams/{team_id}/checkins", headers=m1).json()
    _assert_no_forbidden(checks, "checkins")

    client.post(f"{API}/teams/{team_id}/bill", json={"total_amount": "100"}, headers=leader)
    for h in (leader, m1):
        code = client.get(f"{API}/teams/{team_id}/checkins/me", headers=h).json()["checkin_code"]
        client.post(f"{API}/teams/{team_id}/checkin", json={"checkin_code": code}, headers=h)
    bill = client.get(f"{API}/teams/{team_id}/bill", headers=m1).json()
    _assert_no_forbidden(bill, "bill")
    for p in bill["payments"]:
        assert set(p["user"].keys()) == {"nickname", "age", "gender"}


def test_no_public_user_profile_endpoint(client):
    """匿名模式强约束：不提供公开用户主页端点"""
    headers, _ = make_verified_user(client, "npp")
    r = client.get(f"{API}/users/1", headers=headers)
    assert r.status_code in (404, 405)


def test_unverified_user_blocked_everywhere(client):
    """实名强校验：未实名用户无法浏览/报名任何组队"""
    register(client, "uv1")
    data = register(client, "uv2")
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    assert client.get(f"{API}/plaza/teams", headers=headers).status_code == 403

    v_headers, _ = make_verified_user(client, "uv_leader")
    team_id = create_team(client, v_headers, target_size=3)
    publish_team(client, v_headers, team_id)
    assert client.post(f"{API}/teams/{team_id}/join", headers=headers).status_code == 403
    assert client.post(f"{API}/teams", json={"name": "x", "mode": "invite"}, headers=headers).status_code == 403


def test_my_teams_desensitized(client):
    headers, _ = make_verified_user(client, "mt1")
    team_id = create_team(client, headers, target_size=2)
    my = client.get(f"{API}/users/me/teams", headers=headers).json()
    _assert_no_forbidden(my, "my_teams")
    assert my["groups"]["draft"][0]["id"] == team_id


def test_restaurant_and_dish_fields_desensitized(client):
    """餐馆/菜品为静态参考数据，出站字段不得夹带用户身份信息"""
    from tests.conftest import make_restaurant

    headers, _ = make_verified_user(client, "pr1")
    rid, dish_ids = make_restaurant(client, name="隐私测试餐馆", cuisine="火锅", dish_count=2)
    team_id = create_team(client, headers, restaurant_id=rid, dish_ids=dish_ids)
    publish_team(client, headers, team_id)

    card = client.get(f"{API}/plaza/teams", headers=headers).json()
    _assert_no_forbidden(card, "plaza-with-restaurant")
    detail = client.get(f"{API}/teams/{team_id}", headers=headers).json()
    _assert_no_forbidden(detail, "detail-with-dishes")
    rest = client.get(f"{API}/restaurants/{rid}", headers=headers).json()
    _assert_no_forbidden(rest, "restaurant")

    # 菜品快照键集固定，不含任何用户标识
    assert set(detail["dishes"][0].keys()) == {"dish_id", "name", "price", "image"}
    assert set(rest["dishes"][0].keys()) == {"id", "name", "price", "category", "tags", "image"}
