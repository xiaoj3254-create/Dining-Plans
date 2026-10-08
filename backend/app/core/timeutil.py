"""统一时间语义（全项目唯一时间入口）。

背景：原实现全链路用 `datetime.now()` + naive datetime，服务器时区一旦是 UTC
（容器默认），"就餐时间必须晚于当前"与"核销超时窗口"会整体偏移 8 小时。

约定：
- **内部**：一律使用"配置时区（默认 +08:00）下的 naive 本地时间"，与 SQLite
  `DateTime` 列保持一致，不做任何字符串时区转换；
- **入站**：客户端时间统一经 `to_local_naive()` 归一（带偏移则换算，裸时间按配置时区解释）；
- **出站**：统一经 `iso()` 输出带偏移的 ISO 8601，客户端可自行换算。
"""

from datetime import datetime, timedelta, timezone

from app.core.config import settings

APP_TZ = timezone(timedelta(hours=settings.TIMEZONE_OFFSET_HOURS))


def now() -> datetime:
    """当前时间：按配置时区取墙上时间，去掉 tzinfo（内部统一的 naive 本地时间）。"""
    return datetime.now(APP_TZ).replace(tzinfo=None)


def now_offset_label() -> str:
    """当前生效时区标签，如 +08:00（启动日志/健康检查用）。"""
    total = settings.TIMEZONE_OFFSET_HOURS
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    return f"{sign}{total:02d}:00"


def to_local_naive(dt: datetime | None) -> datetime | None:
    """把任意来源的 datetime 归一到配置时区的 naive 本地时间。

    - 带 tzinfo：先换算到目标时区，再去掉 tzinfo；
    - naive：视为已经是目标时区的墙上时间（前端提交的本地时间即此语义）。
    """
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(APP_TZ).replace(tzinfo=None)
    return dt


def iso(dt: datetime | None) -> str | None:
    """出站：naive 本地时间 → 带偏移的 ISO 8601（2026-10-07T20:00:00+08:00）。"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=APP_TZ)
    return dt.isoformat(timespec="seconds")
