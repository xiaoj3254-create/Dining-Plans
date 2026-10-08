"""M7 验收：餐馆与菜品参考数据（列表/筛选/搜索/详情/权限）"""

from tests.conftest import API, make_restaurant, make_verified_user, register


def _seed_two(client):
    rid1, dish_ids = make_restaurant(client, name="蜀九香老灶火锅", cuisine="火锅",
                                     district="国贸商圈", avg_price=118, dish_count=3)
    rid2, _ = make_restaurant(client, name="一膳寿司", cuisine="日料",
                              district="三里屯", avg_price=156, dish_count=2)
    return rid1, rid2, dish_ids


def test_list_restaurants_with_filters(client):
    headers, _ = make_verified_user(client, "rlist")
    rid1, rid2, _ = _seed_two(client)

    r = client.get(f"{API}/restaurants", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert {x["id"] for x in body["restaurants"]} == {rid1, rid2}

    # 菜系筛选
    hotpot = client.get(f"{API}/restaurants?cuisine=火锅", headers=headers).json()
    assert [x["name"] for x in hotpot["restaurants"]] == ["蜀九香老灶火锅"]

    # 关键词命中餐馆名
    by_name = client.get(f"{API}/restaurants?keyword=蜀九香", headers=headers).json()
    assert by_name["total"] == 1
    # 关键词命中商圈
    by_district = client.get(f"{API}/restaurants?keyword=三里屯", headers=headers).json()
    assert by_district["total"] == 1
    assert by_district["restaurants"][0]["cuisine_type"] == "日料"


def test_restaurant_detail_with_dishes(client):
    headers, _ = make_verified_user(client, "rdetail")
    rid, _, dish_ids = _seed_two(client)

    d = client.get(f"{API}/restaurants/{rid}", headers=headers).json()
    assert d["name"] == "蜀九香老灶火锅"
    assert d["avg_price"] == 118.0
    assert d["dish_count"] == 3
    assert [x["id"] for x in d["dishes"]] == dish_ids
    # 图片出站统一为小程序包内路径
    assert d["image"] == "/static/food/rest_test.png"
    assert all(x["image"].startswith("/static/food/") for x in d["dishes"])

    # 单独取菜品清单
    dl = client.get(f"{API}/restaurants/{rid}/dishes", headers=headers).json()
    assert dl["total"] == 3
    # 分类过滤
    cat = d["dishes"][0]["category"]
    f = client.get(f"{API}/restaurants/{rid}/dishes?category={cat}", headers=headers).json()
    assert f["total"] >= 1


def test_restaurant_not_found_404(client):
    headers, _ = make_verified_user(client, "r404")
    _seed_two(client)
    assert client.get(f"{API}/restaurants/99999", headers=headers).status_code == 404
    assert client.get(f"{API}/restaurants/99999/dishes", headers=headers).status_code == 404


def test_restaurant_requires_verified(client):
    """未实名用户不可浏览餐馆（与广场口径一致）"""
    register(client, "r_unverified")
    data = register(client, "r_unverified2")
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    assert client.get(f"{API}/restaurants", headers=headers).status_code == 403
