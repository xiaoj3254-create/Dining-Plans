"""★ M3 验收核心：并发抢名额不超卖。

用 httpx.AsyncClient + ASGITransport 在同一事件循环内并发发起请求，
FastAPI 同步端点跑在线程池 → 多线程多连接真实并发写 SQLite。
"""

import asyncio

import httpx
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import API, create_team, make_verified_user, publish_team, register, realname


def _setup_team(tmp_path, target_size=3, n_waiters=10):
    app = create_app(f"sqlite:///{(tmp_path / 'conc.db').as_posix()}")
    with TestClient(app) as c:
        leader_h, _ = make_verified_user(c, "cleader")
        team_id = create_team(c, leader_h, target_size=target_size)
        publish_team(c, leader_h, team_id)
        tokens = []
        for i in range(n_waiters):
            d = register(c, f"waiter{i}")
            realname(c, {"Authorization": f"Bearer {d['access_token']}"})
            tokens.append(d["access_token"])
    return app, leader_h["Authorization"], team_id, tokens


def test_concurrent_join_no_oversell(tmp_path):
    """target_size 含队长：可被抢的名额 = target_size - 1"""
    target_size, n = 3, 10
    expected_slots = target_size - 1
    app, leader_auth, team_id, tokens = _setup_team(tmp_path, target_size, n)

    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:

            async def join(i):
                r = await ac.post(f"{API}/teams/{team_id}/join",
                                  headers={"Authorization": f"Bearer {tokens[i]}"})
                return r.status_code

            results = await asyncio.gather(*[join(i) for i in range(n)])
        await transport.aclose()
        return results

    results = asyncio.run(run())
    ok = [s for s in results if s == 200]
    rejected = [s for s in results if s == 409]
    assert len(ok) == expected_slots, f"应恰好 {expected_slots} 人成功，实际 {len(ok)}: {results}"
    assert len(rejected) == n - expected_slots
    assert all(s == 200 for s in results if s != 409)  # 不应出现 500

    # 终态校验：current_size == target_size，状态 formed
    with TestClient(app) as c:
        r = c.get(f"{API}/teams/{team_id}", headers={"Authorization": leader_auth})
        d = r.json()
        assert d["current_size"] == target_size
        assert d["status"] == "formed"
        assert len(d["members"]) == target_size


def test_concurrent_join_by_link_no_oversell(tmp_path):
    target_size, n = 2, 8
    expected_slots = target_size - 1
    app = create_app(f"sqlite:///{(tmp_path / 'conc2.db').as_posix()}")
    with TestClient(app) as c:
        leader_h, _ = make_verified_user(c, "cleader2")
        team_id = create_team(c, leader_h, mode="invite", target_size=target_size)
        code = publish_team(c, leader_h, team_id)["code"]
        tokens = []
        for i in range(n):
            d = register(c, f"linker{i}")
            realname(c, {"Authorization": f"Bearer {d['access_token']}"})
            tokens.append(d["access_token"])

    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:

            async def join(i):
                r = await ac.post(f"{API}/teams/join/{code}",
                                  headers={"Authorization": f"Bearer {tokens[i]}"})
                return r.status_code

            return await asyncio.gather(*[join(i) for i in range(n)])

    results = asyncio.run(run())
    assert sorted(r == 200 for r in results).count(True) == expected_slots
    with TestClient(app) as c:
        d = c.get(f"{API}/teams/{team_id}", headers={"Authorization": leader_h["Authorization"]}).json()
        assert d["current_size"] == target_size and d["status"] == "formed"
