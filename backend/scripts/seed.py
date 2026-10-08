"""演示数据 seed：参考数据（餐馆 + 菜品）落库，再创建 5 支不同状态的队伍。

餐馆/菜品来自 scripts/menu_catalog.json（与前端图片生成脚本共用同一份清单）；
队伍仍走 HTTP API，以保证经过状态机（自动成团等）。

运行：python scripts/seed.py
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, ".")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.main import create_app  # noqa: E402
from app.models.dish import Dish  # noqa: E402
from app.models.restaurant import Restaurant  # noqa: E402

CATALOG = Path(__file__).resolve().parent / "menu_catalog.json"
API = "/api"


def new_session():
    """必须在 create_app() 之后调用：SessionLocal 由 init_db() 在运行时绑定"""
    from app.db import SessionLocal

    return SessionLocal()


def load_catalog() -> dict:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def seed_reference_data(db, catalog: dict) -> None:
    """餐馆 + 菜品落库（幂等：已有参考数据则跳过）"""
    if db.execute(select(Restaurant.id)).first() is not None:
        print("参考数据已存在，跳过餐馆/菜品写入")
        return
    pools = catalog["dish_pools"]
    for i, r in enumerate(catalog["restaurants"]):
        rest = Restaurant(
            name=r["name"], cuisine_type=r["cuisine_type"], district=r["district"],
            avg_price=r["avg_price"], description=r["description"],
            image=r["image"], sort_order=i,
            # 坐标用于广场「距离」标签与距离排序（menu_catalog.json 单一数据源）
            latitude=r.get("latitude"), longitude=r.get("longitude"),
        )
        db.add(rest)
        db.flush()
        pool = {d["name"]: d for d in pools[r["cuisine_type"]]}
        for j, dname in enumerate(r["dish_names"]):
            d = pool[dname]
            db.add(Dish(
                restaurant_id=rest.id, name=d["name"], price=d["price"],
                category=d["category"], tags=d.get("tags") or None,
                image=d["file"], sort_order=j,
            ))
    db.commit()
    dish_total = len(db.execute(select(Dish.id)).all())
    print(f"参考数据：{len(catalog['restaurants'])} 家餐馆 / {dish_total} 道菜")


def resolve(db, restaurant_name: str, dish_names: list):
    """按名称解析出 restaurant_id 与 dish_ids（供 HTTP 建队使用）"""
    r = db.execute(select(Restaurant).where(Restaurant.name == restaurant_name)).scalar_one()
    rows = db.execute(select(Dish).where(Dish.restaurant_id == r.id)).scalars().all()
    by_name = {d.name: d.id for d in rows}
    return r.id, [by_name[n] for n in dish_names]


def main():
    app = create_app()
    catalog = load_catalog()

    db = new_session()
    try:
        seed_reference_data(db, catalog)
        ref = {
            "hotpot": resolve(db, "蜀九香老灶火锅", ["牛油锅底", "毛肚", "虾滑", "鲜鸭血"]),
            "bbq": resolve(db, "汉拿山韩式烤肉", ["厚切五花肉", "牛舌", "石锅拌饭", "生菜拼盘"]),
            "sushi": resolve(db, "一膳寿司", ["三文鱼刺身", "鳗鱼饭", "味增汤"]),
            "dimsum": resolve(db, "点都德", ["虾饺皇", "叉烧包", "干炒牛河", "老火例汤"]),
            "sichuan": resolve(db, "眉州东坡", ["宫保鸡丁", "水煮鱼", "担担面"]),
        }
    finally:
        db.close()

    with TestClient(app) as c:
        def mk(name, gender="male", age=26):
            d = c.post(f"{API}/auth/register", json={
                "username": name, "password": "pass123456",
                "nickname": name, "age": age, "gender": gender,
            }).json()
            h = {"Authorization": f"Bearer {d['access_token']}"}
            c.post(f"{API}/users/me/realname",
                   json={"real_name": name, "id_card": "110101199001010000"}, headers=h)
            return h

        leader = mk("demo_leader")
        a1 = mk("demo_a1", "female", 24)
        a2 = mk("demo_a2", "male", 29)
        a3 = mk("demo_a3", "female", 27)

        def make_team(name, mode, size, ref_key, cuisine, days, members_):
            rid, dish_ids = ref[ref_key]
            r = c.post(f"{API}/teams", json={
                "name": name, "mode": mode, "target_size": size,
                "cuisine_type": cuisine, "menu_summary": "预选菜品见菜单",
                "location_hint": "", "restaurant_id": rid, "dish_ids": dish_ids,
                "dining_time": (datetime.now() + timedelta(days=days)).isoformat(timespec="seconds"),
            }, headers=leader)
            tid = r.json()["id"]
            c.post(f"{API}/teams/{tid}/publish", headers=leader)
            for h in members_:
                c.post(f"{API}/teams/{tid}/join", headers=h)
            return tid

        # 1) 招募中：火锅（invite，3/4）
        t1 = make_team("周五晚火锅局", "invite", 4, "hotpot", "火锅", 2, [a1, a2])
        print(f"[招募中 3/4] 周五晚火锅局 → 蜀九香老灶火锅  team_id={t1}")

        # 2) 已成团：烤肉（anonymous，4/4，已核销 2）
        t2 = make_team("周六烤肉小聚", "anonymous", 4, "bbq", "烤肉", 1, [a1, a2, a3])
        for h in (leader, a1):
            code = c.get(f"{API}/teams/{t2}/checkins/me", headers=h).json()["checkin_code"]
            c.post(f"{API}/teams/{t2}/checkin", json={"checkin_code": code}, headers=h)
        print(f"[已成团 4/4·已核销2] 周六烤肉小聚 → 汉拿山韩式烤肉  team_id={t2}")

        # 3) 招募中：日料（invite，2/3）
        t3 = make_team("周三午间日料", "invite", 3, "sushi", "日料", 3, [a1])
        print(f"[招募中 2/3] 周三午间日料 → 一膳寿司  team_id={t3}")

        # 4) 招募中：粤菜早茶（anonymous，3/4）
        t4 = make_team("周末早茶局", "anonymous", 4, "dimsum", "粤菜", 2, [a1, a2])
        print(f"[招募中 3/4] 周末早茶局 → 点都德  team_id={t4}")

        # 5) 已成团：川菜（anonymous，2/2 满员自动成团）
        t5 = make_team("川菜小聚", "anonymous", 2, "sichuan", "川菜", 1, [a1])
        print(f"[已成团 2/2] 川菜小聚 → 眉州东坡  team_id={t5}")

        print("\n演示账号（密码均为 pass123456）：demo_leader / demo_a1 / demo_a2 / demo_a3")
        print("或在小程序「我的-演示工具」中直接切换账号名 demo_leader / demo_a1 …")
        print("参考数据：5 支队伍已分别挂上餐馆与预选菜品，可在队伍详情查看菜品网格与预估人均")


if __name__ == "__main__":
    main()
