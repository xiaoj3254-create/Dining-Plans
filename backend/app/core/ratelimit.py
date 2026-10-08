"""进程内滑动窗口限流。

与 WS 连接管理器同样的取舍：本项目是单进程单 worker 部署，
进程内计数就是全局计数，无需引入 Redis。

覆盖场景：注册/登录爆破、邀请码遍历（配合加长后的邀请码）、
群聊洪水、报名挤占名额、踢人刷屏。
"""

import threading
import time
from collections import deque

from fastapi import HTTPException, Request

from app.core.config import settings

WINDOW_SECONDS = 60.0
_MAX_BUCKETS = 20000  # 兜底清理阈值，防止被随机 IP 撑爆内存

_buckets: dict[str, deque] = {}
_lock = threading.Lock()


def _prune(now: float) -> None:
    if len(_buckets) < _MAX_BUCKETS:
        return
    for key in [k for k, q in _buckets.items() if not q or now - q[-1] > WINDOW_SECONDS]:
        _buckets.pop(key, None)


def check(scope: str, identity: str | int | None, limit: int) -> None:
    """计数一次；超限抛 429。limit <= 0 或限流关闭时直接放行。"""
    if not settings.RATE_LIMIT_ENABLED or limit <= 0:
        return
    key = f"{scope}:{identity or 'anon'}"
    now = time.monotonic()
    with _lock:
        _prune(now)
        q = _buckets.setdefault(key, deque())
        while q and now - q[0] > WINDOW_SECONDS:
            q.popleft()
        if len(q) >= limit:
            raise HTTPException(
                status_code=429,
                detail=f"操作过于频繁（{scope} 每分钟最多 {limit} 次），请稍后再试",
            )
        q.append(now)


def reset() -> None:
    """测试用：清空计数。"""
    with _lock:
        _buckets.clear()


def client_ip(request: Request) -> str:
    """取客户端 IP（小程序侧一般无 XFF，取直连地址即可）。"""
    if request.client and request.client.host:
        return request.client.host
    return "unknown"
