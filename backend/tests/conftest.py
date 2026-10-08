"""pytest 基础设施：文件 SQLite（支持跨连接并发测试）+ TestClient + 常用辅助"""

import os
import sys
import tempfile

import pytest

# 测试环境关闭限流：整个套件在同一分钟内会发起远超限额的认证请求，
# 且限流按客户端 IP 计数，测试里所有请求都来自同一个 TestClient。
os.environ.setdefault("DP_RATE_LIMIT_ENABLED", "false")
# 上传目录指向临时目录：避免测试把图片写进 backend/uploads
os.environ.setdefault("DP_UPLOAD_DIR", os.path.join(tempfile.mkdtemp(prefix="dp-uploads-"), "uploads"))

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # noqa: E402

# 校验位合法的测试身份证（GB 11643）：110101 1990-01-01 末尾校验码 7
VALID_ID_CARD = "110101199001011237"


@pytest.fixture()
def db_url(tmp_path):
    return f"sqlite:///{(tmp_path / 'test.db').as_posix()}"


@pytest.fixture()
def client(db_url):
    from app.core import ratelimit

    ratelimit.reset()
    app = create_app(db_url)
    with TestClient(app) as c:
        yield c


# ---------- REST 辅助 ----------

API = "/api"


def register(client, username, nickname=None, age=25, gender="male", consent=True):
    r = client.post(f"{API}/auth/register", json={
        "username": username, "password": "pass123456",
        "nickname": nickname or username, "age": age, "gender": gender,
        "consent": consent,
    })
    assert r.status_code == 200, r.text
    return r.json()


def realname(client, headers, real_name="张三", id_card=VALID_ID_CARD, consent=True):
    r = client.post(f"{API}/users/me/realname",
                    json={"real_name": real_name, "id_card": id_card, "consent": consent},
                    headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def make_verified_user(client, username, **kw):
    """注册 + 实名，返回 (headers, user_id)"""
    data = register(client, username, **kw)
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    user_id = data["user"]["id"]
    realname(client, headers)
    return headers, user_id


def make_restaurant(client, name="测试餐馆", cuisine="火锅", district="测试商圈",
                    avg_price=100, dish_count=2, latitude=39.9088, longitude=116.4613):
    """直插参考数据（餐馆 + N 道菜），返回 (restaurant_id, [dish_id, ...])。

    参考数据是只读资料表，没有写接口，因此测试里直接落库。
    默认给一组坐标（国贸附近），使距离相关断言无需每个用例重复设置。
    """
    from app.db import SessionLocal
    from app.models.dish import Dish
    from app.models.restaurant import Restaurant

    db = SessionLocal()
    try:
        rest = Restaurant(
            name=name, cuisine_type=cuisine, district=district,
            avg_price=avg_price, description="测试餐馆", image="rest_test.png",
            latitude=latitude, longitude=longitude,
        )
        db.add(rest)
        db.flush()
        dish_ids = []
        for i in range(dish_count):
            d = Dish(
                restaurant_id=rest.id, name=f"{cuisine}菜品{i + 1}"[:50],
                price=30 + i * 10, category="荤菜" if i % 2 == 0 else "素菜",
                tags="招牌" if i == 0 else None, image=f"dish_test_{i + 1}.png", sort_order=i,
            )
            db.add(d)
            db.flush()
            dish_ids.append(d.id)
        db.commit()
        return rest.id, dish_ids
    finally:
        db.close()


def create_team(client, headers, name="周末火锅局", mode="invite", target_size=3,
                cuisine="火锅", dining_days=1, restaurant_id=None, dish_ids=None, **kw):
    import datetime
    payload = {
        "name": name, "mode": mode, "target_size": target_size,
        "cuisine_type": cuisine,
        "dining_time": (datetime.datetime.now() + datetime.timedelta(days=dining_days)).isoformat(),
    }
    # 餐馆为发布必填项：未显式指定时自动补一家测试餐馆
    if restaurant_id is None and "restaurant_id" not in kw:
        restaurant_id, _ = make_restaurant(client, name=f"测试餐馆-{name}"[:50], cuisine=cuisine)
    if restaurant_id is not None:
        payload["restaurant_id"] = restaurant_id
    if dish_ids:
        payload["dish_ids"] = dish_ids
    payload.update(kw)
    r = client.post(f"{API}/teams", json=payload, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def publish_team(client, headers, team_id):
    r = client.post(f"{API}/teams/{team_id}/publish", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def full_flow_formed(client, leader_headers, member_headers_list, team_id):
    """辅助：发布 + 依次加入直至满员成团，返回队伍详情"""
    publish_team(client, leader_headers, team_id)
    for h in member_headers_list:
        r = client.post(f"{API}/teams/{team_id}/join", headers=h)
        assert r.status_code == 200, r.text
    return client.get(f"{API}/teams/{team_id}", headers=leader_headers).json()
