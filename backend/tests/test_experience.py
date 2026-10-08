"""2026-10-08 体验优化（广场/详情/群聊）配套回归测试。"""

import datetime
import io
import struct
import zlib

from app.core.config import settings
from app.core.timeutil import now
from tests.conftest import (
    API,
    create_team,
    full_flow_formed,
    make_restaurant,
    make_verified_user,
    publish_team,
)


def _png_bytes() -> bytes:
    """生成一个 1x1 的最小合法 PNG（带正确 IHDR/IDAT/IEND 与 CRC）。"""
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    raw = b"\x00\xff\x00\x00"  # 一行，filter=0，RGB 红点
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def _future(hours=3):
    return (datetime.datetime.now() + datetime.timedelta(hours=hours)).isoformat()


def _team_at(client, headers, name, dining_hours, restaurant_id, target_size=3):
    return create_team(client, headers, target_size=target_size, name=name,
                       restaurant_id=restaurant_id, dining_days=0)


def _set_dining_time(team_id: int, when: datetime.datetime):
    from app import db as database
    from app.models.team import Team

    db = database.SessionLocal()
    try:
        t = db.get(Team, team_id)
        t.dining_time = when
        db.commit()
    finally:
        db.close()


# ---------- 广场：用餐时段筛选 ----------

def test_plaza_meal_period_filter(client):
    headers, _ = make_verified_user(client, "mp_L")
    rid, _ = make_restaurant(client, name="时段餐馆")

    lunch_id = create_team(client, headers, target_size=3, name="午市局", restaurant_id=rid)
    dinner_id = create_team(client, headers, target_size=3, name="晚市局", restaurant_id=rid)
    publish_team(client, headers, lunch_id)
    publish_team(client, headers, dinner_id)

    today = now().date()
    _set_dining_time(lunch_id, datetime.datetime.combine(today + datetime.timedelta(days=3), datetime.time(12, 30)))
    _set_dining_time(dinner_id, datetime.datetime.combine(today + datetime.timedelta(days=3), datetime.time(19, 0)))

    lunch = client.get(f"{API}/plaza/teams?meal_period=lunch", headers=headers).json()
    ids = [t["id"] for t in lunch["teams"]]
    assert lunch_id in ids and dinner_id not in ids

    dinner = client.get(f"{API}/plaza/teams?meal_period=dinner", headers=headers).json()
    ids2 = [t["id"] for t in dinner["teams"]]
    assert dinner_id in ids2 and lunch_id not in ids2

    # 非法时段值由服务层拦截（多值参数不再受 Query pattern 约束）
    assert client.get(f"{API}/plaza/teams?meal_period=midnight", headers=headers).status_code == 422


def test_plaza_multi_select_filters(client):
    """多选筛选：菜系与时段支持逗号分隔多值，维度内取并集。"""
    headers, _ = make_verified_user(client, "multi_L")
    hot_rid, _ = make_restaurant(client, name="多选火锅店", cuisine="火锅")
    bbq_rid, _ = make_restaurant(client, name="多选烧烤店", cuisine="烧烤")
    sus_rid, _ = make_restaurant(client, name="多选寿司店", cuisine="日料")

    hot_id = create_team(client, headers, name="火锅午市", cuisine="火锅",
                         restaurant_id=hot_rid, target_size=3)
    bbq_id = create_team(client, headers, name="烧烤晚市", cuisine="烧烤",
                         restaurant_id=bbq_rid, target_size=3)
    sus_id = create_team(client, headers, name="日料晚市", cuisine="日料",
                         restaurant_id=sus_rid, target_size=3)
    for tid in (hot_id, bbq_id, sus_id):
        publish_team(client, headers, tid)

    today = now().date()
    _set_dining_time(hot_id, datetime.datetime.combine(today + datetime.timedelta(days=3), datetime.time(12, 30)))
    _set_dining_time(bbq_id, datetime.datetime.combine(today + datetime.timedelta(days=3), datetime.time(19, 0)))
    _set_dining_time(sus_id, datetime.datetime.combine(today + datetime.timedelta(days=3), datetime.time(19, 30)))

    # 菜系多选：火锅 + 烧烤 → 命中两支，排除日料
    r = client.get(f"{API}/plaza/teams?cuisine=火锅,烧烤", headers=headers).json()
    ids = [t["id"] for t in r["teams"]]
    assert hot_id in ids and bbq_id in ids and sus_id not in ids

    # 时段多选：午市 + 晚市 → 三支全中
    r2 = client.get(f"{API}/plaza/teams?meal_period=lunch,dinner", headers=headers).json()
    ids2 = [t["id"] for t in r2["teams"]]
    assert {hot_id, bbq_id, sus_id} <= set(ids2)

    # 单值仍旧可用（向后兼容）
    r3 = client.get(f"{API}/plaza/teams?cuisine=日料", headers=headers).json()
    assert [t["id"] for t in r3["teams"]] == [sus_id]

    # 跨维度组合：菜系多选 + 时段多选可叠加（火锅或烧烤，且 午市或晚市 → 命中火锅午市 + 烧烤晚市）
    r4 = client.get(
        f"{API}/plaza/teams?cuisine=火锅,烧烤&meal_period=lunch,dinner", headers=headers
    ).json()
    assert {t["id"] for t in r4["teams"]} == {hot_id, bbq_id}

    # 部分非法值：取合法部分，不报错
    r5 = client.get(f"{API}/plaza/teams?meal_period=lunch,midnight", headers=headers)
    assert r5.status_code == 200
    assert [t["id"] for t in r5.json()["teams"]] == [hot_id]


# ---------- 广场：距离排序与半径筛选 ----------

def test_plaza_distance_sort_and_radius(client):
    headers, _ = make_verified_user(client, "dist_L")
    # 两家店相距 ~20km（用坐标拉开差距）
    near_rid, _ = make_restaurant(client, name="近店")
    far_rid, _ = make_restaurant(client, name="远店")
    from app import db as database
    from app.models.restaurant import Restaurant

    db = database.SessionLocal()
    try:
        db.get(Restaurant, near_rid).latitude, db.get(Restaurant, near_rid).longitude = 39.9088, 116.4613
        db.get(Restaurant, far_rid).latitude, db.get(Restaurant, far_rid).longitude = 40.0025, 116.4700
        db.commit()
    finally:
        db.close()

    near_id = create_team(client, headers, target_size=3, name="近局", restaurant_id=near_rid)
    far_id = create_team(client, headers, target_size=3, name="远局", restaurant_id=far_rid)
    publish_team(client, headers, near_id)
    publish_team(client, headers, far_id)
    # 远店的队伍就餐时间更早，确保"按时间排序"与"按距离排序"结果不同
    _set_dining_time(near_id, now() + datetime.timedelta(days=5))
    _set_dining_time(far_id, now() + datetime.timedelta(days=1))

    # 站在近店附近
    lat, lng = 39.9088, 116.4613
    by_time = client.get(f"{API}/plaza/teams?sort=time&lat={lat}&lng={lng}", headers=headers).json()
    assert [t["id"] for t in by_time["teams"]][:2] == [far_id, near_id]

    by_dist = client.get(f"{API}/plaza/teams?sort=distance&lat={lat}&lng={lng}", headers=headers).json()
    assert by_dist["sort"] == "distance"
    assert [t["id"] for t in by_dist["teams"]][:2] == [near_id, far_id]
    near_card = next(t for t in by_dist["teams"] if t["id"] == near_id)
    far_card = next(t for t in by_dist["teams"] if t["id"] == far_id)
    assert near_card["distance_km"] < 1.0
    assert far_card["distance_km"] > 5.0

    # 半径筛选：只留近店
    within = client.get(
        f"{API}/plaza/teams?sort=distance&lat={lat}&lng={lng}&max_distance_km=5", headers=headers
    ).json()
    ids = [t["id"] for t in within["teams"]]
    assert near_id in ids and far_id not in ids

    # 不带坐标时不产生距离字段
    plain = client.get(f"{API}/plaza/teams", headers=headers).json()
    assert all(t["distance_km"] is None for t in plain["teams"])


def test_plaza_card_has_recruit_deadline(client):
    headers, _ = make_verified_user(client, "rd_L")
    rid, _ = make_restaurant(client, name="截止餐馆")
    tid = create_team(client, headers, target_size=3, name="截止局", restaurant_id=rid)
    publish_team(client, headers, tid)
    card = next(t for t in client.get(f"{API}/plaza/teams", headers=headers).json()["teams"]
                if t["id"] == tid)
    assert card["recruit_deadline"]
    # 截止时间 = 就餐时间 + 招募宽限期，必然晚于就餐时间
    assert card["recruit_deadline"] > card["dining_time"]


# ---------- 招募期修改饭局 ----------

def test_recruiting_edit_notifies_members(client):
    leader, _ = make_verified_user(client, "re_L")
    member, _ = make_verified_user(client, "re_M")
    rid, _ = make_restaurant(client, name="修改餐馆")
    tid = create_team(client, leader, target_size=4, name="改前", restaurant_id=rid)
    publish_team(client, leader, tid)
    client.post(f"{API}/teams/{tid}/join", headers=member)

    r = client.patch(f"{API}/teams/{tid}", json={"name": "改后", "menu_summary": "加个毛肚"}, headers=leader)
    assert r.status_code == 200, r.text
    d = client.get(f"{API}/teams/{tid}", headers=leader).json()
    assert d["name"] == "改后"
    assert d["status"] == "recruiting"

    items = client.get(f"{API}/notifications", headers=member).json()["items"]
    updated = [n for n in items if n["type"] == "team_updated"]
    assert updated, "队员应收到「队长修改了饭局」通知"
    assert updated[0]["team_id"] == tid


def test_recruiting_edit_guards(client):
    leader, _ = make_verified_user(client, "rg_L")
    m1, _ = make_verified_user(client, "rg_M1")
    m2, _ = make_verified_user(client, "rg_M2")
    rid, _ = make_restaurant(client, name="守卫餐馆")
    tid = create_team(client, leader, target_size=4, name="守卫局", restaurant_id=rid)
    publish_team(client, leader, tid)
    client.post(f"{API}/teams/{tid}/join", headers=m1)
    client.post(f"{API}/teams/{tid}/join", headers=m2)  # 3/4

    # 目标人数不能小于已入队人数
    r = client.patch(f"{API}/teams/{tid}", json={"target_size": 2}, headers=leader)
    assert r.status_code == 422
    # 已发布不可改组队模式
    r2 = client.patch(f"{API}/teams/{tid}", json={"mode": "anonymous"}, headers=leader)
    assert r2.status_code == 422
    # 就餐时间不能改成过去
    r3 = client.patch(f"{API}/teams/{tid}", json={
        "dining_time": (now() - datetime.timedelta(hours=1)).isoformat()}, headers=leader)
    assert r3.status_code == 422
    # 非队长不能改
    assert client.patch(f"{API}/teams/{tid}", json={"name": "偷袭"},
                        headers=m1).status_code == 403


def test_recruiting_edit_to_full_forms_team(client):
    """队长把人数改到刚好满员 → 立即成团，不留"剩余 0 人却仍在招募"的僵尸状态"""
    leader, _ = make_verified_user(client, "rf_L")
    m1, _ = make_verified_user(client, "rf_M1")
    rid, _ = make_restaurant(client, name="改满餐馆")
    tid = create_team(client, leader, target_size=4, name="改满局", restaurant_id=rid)
    publish_team(client, leader, tid)
    client.post(f"{API}/teams/{tid}/join", headers=m1)  # 2/4

    r = client.patch(f"{API}/teams/{tid}", json={"target_size": 2}, headers=leader)
    assert r.status_code == 200, r.text
    d = client.get(f"{API}/teams/{tid}", headers=leader).json()
    assert d["status"] == "formed"
    assert d["remaining"] == 0
    # 账单未生效，队员仍可退出（队长本人永远不可退）
    assert d["can_leave"] is False
    member_view = client.get(f"{API}/teams/{tid}", headers=m1).json()
    assert member_view["can_leave"] is True


# ---------- 群聊：图片与 @全体 ----------

def _formed_team(client, name):
    leader, leader_id = make_verified_user(client, name + "L")
    member, member_id = make_verified_user(client, name + "M")
    rid, _ = make_restaurant(client, name=f"{name}餐馆")
    tid = create_team(client, leader, target_size=2, name=name, restaurant_id=rid)
    full_flow_formed(client, leader, [member], tid)
    return tid, leader, leader_id, member, member_id


def test_chat_image_upload_and_send(client):
    tid, leader, _, member, _ = _formed_team(client, "图聊")

    # 上传合法 PNG
    r = client.post(
        f"{API}/teams/{tid}/uploads",
        files={"file": ("随便的名字.png", io.BytesIO(_png_bytes()), "image/png")},
        headers=leader,
    )
    assert r.status_code == 200, r.text
    url = r.json()["url"]
    # 文件名由服务端随机生成，不含客户端原始名
    assert url.startswith("/uploads/chat/") and "随便" not in url

    # 以图片消息发出
    msg = client.post(f"{API}/teams/{tid}/messages",
                      json={"content": url, "msg_type": "image"}, headers=leader)
    assert msg.status_code == 200, msg.text
    assert msg.json()["msg_type"] == "image"

    # 非成员不能上传
    outsider, _ = make_verified_user(client, "图聊O")
    assert client.post(
        f"{API}/teams/{tid}/uploads",
        files={"file": ("a.png", io.BytesIO(_png_bytes()), "image/png")},
        headers=outsider,
    ).status_code == 403

    # 上传的图片可被静态托管读取
    assert client.get(url).status_code == 200


def test_chat_upload_rejects_bad_input(client):
    tid, leader, _, _, _ = _formed_team(client, "图验")

    # 非白名单 MIME
    r = client.post(f"{API}/teams/{tid}/uploads",
                    files={"file": ("a.svg", io.BytesIO(b"<svg/>"), "image/svg+xml")},
                    headers=leader)
    assert r.status_code == 422

    # 伪装成 png 的非图片内容（魔数校验）
    r2 = client.post(f"{API}/teams/{tid}/uploads",
                     files={"file": ("a.png", io.BytesIO(b"not an image at all"), "image/png")},
                     headers=leader)
    assert r2.status_code == 422

    # 超限大小
    old = settings.UPLOAD_MAX_BYTES
    settings.UPLOAD_MAX_BYTES = 10
    try:
        r3 = client.post(f"{API}/teams/{tid}/uploads",
                         files={"file": ("a.png", io.BytesIO(_png_bytes()), "image/png")},
                         headers=leader)
        assert r3.status_code == 413
    finally:
        settings.UPLOAD_MAX_BYTES = old

    # 外链图片不能作为图片消息（防盗图/防钓鱼）
    r4 = client.post(f"{API}/teams/{tid}/messages",
                     json={"content": "https://example.com/a.png", "msg_type": "image"},
                     headers=leader)
    assert r4.status_code == 422


def test_chat_mentions_all_only_leader(client):
    tid, leader, _, member, _ = _formed_team(client, "提及")

    ok = client.post(f"{API}/teams/{tid}/messages",
                     json={"content": "大家注意", "mentions_all": True}, headers=leader)
    assert ok.status_code == 200
    assert ok.json()["mentions_all"] is True

    denied = client.post(f"{API}/teams/{tid}/messages",
                         json={"content": "我也@全体", "mentions_all": True}, headers=member)
    assert denied.status_code == 403

    normal = client.post(f"{API}/teams/{tid}/messages",
                         json={"content": "普通消息"}, headers=member)
    assert normal.json()["mentions_all"] is False


def test_chat_recall_image_message(client):
    tid, leader, _, _, _ = _formed_team(client, "图撤")
    up = client.post(f"{API}/teams/{tid}/uploads",
                     files={"file": ("a.png", io.BytesIO(_png_bytes()), "image/png")},
                     headers=leader).json()
    msg = client.post(f"{API}/teams/{tid}/messages",
                      json={"content": up["url"], "msg_type": "image"}, headers=leader).json()
    r = client.post(f"{API}/teams/{tid}/messages/{msg['id']}/recall", headers=leader)
    assert r.status_code == 200 and r.json()["recalled"] is True


# ---------- 账单录入通知 ----------

def test_bill_submitted_notifies_members(client):
    tid, leader, _, member, _ = _formed_team(client, "账单通知")
    r = client.post(f"{API}/teams/{tid}/bill", json={"total_amount": "180"}, headers=leader)
    assert r.status_code == 200, r.text
    items = client.get(f"{API}/notifications", headers=member).json()["items"]
    got = [n for n in items if n["type"] == "bill_submitted"]
    assert got, "账单录入后应通知队员"
    assert got[0]["payload"]["total_amount"] == 180.0
    assert got[0]["category"] == "todo"


# ---------- 我的组队：历史与距离所需字段 ----------

def test_my_teams_has_restaurant_coords_and_deadline(client):
    leader, _ = make_verified_user(client, "mt_L")
    rid, _ = make_restaurant(client, name="我的餐馆")
    tid = create_team(client, leader, target_size=3, name="我的局", restaurant_id=rid)
    publish_team(client, leader, tid)

    groups = client.get(f"{API}/users/me/teams", headers=leader).json()["groups"]
    item = next(t for t in groups["recruiting"] if t["id"] == tid)
    assert item["restaurant"]["latitude"] is not None
    assert item["recruit_deadline"]
    assert item["bill_status"] is None
