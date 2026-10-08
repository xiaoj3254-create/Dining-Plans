import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.timeutil import now_offset_label
from app.workers import task_worker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    worker = asyncio.create_task(task_worker.run_worker(settings.TASK_POLL_INTERVAL))
    reminder = asyncio.create_task(_scan_loop())
    logger.info(
        "后台任务已启动（task_worker + 巡检）；ENV=%s 时区=%s 实名模式=%s 推送通道=%s",
        settings.ENV, now_offset_label(), settings.REALNAME_MODE, settings.PUSH_PROVIDER,
    )
    yield
    worker.cancel()
    reminder.cancel()


async def _scan_loop():
    """巡检总循环：核销超时阶梯提醒 / 账单锁定收口 / 招募超时下架 / 订阅消息出队。"""
    from app.db import SessionLocal
    from app.services import notify_service

    while True:
        await asyncio.sleep(settings.REMINDER_INTERVAL_SECONDS)
        try:
            db = SessionLocal()
            try:
                notify_service.run_all_scans(db)
            finally:
                db.close()
        except Exception:
            logger.exception("巡检异常")


def create_app(db_url: str | None = None) -> FastAPI:
    from fastapi.middleware.cors import CORSMiddleware

    from app import db as database
    from app.api import (auth, bills, chat, checkin, notifications, plaza,
                         reports, restaurants, teams, users, ws)

    # 生产环境 fail-fast：危险默认值（默认 JWT 密钥 / mock 登录 / 通配 CORS）拒绝启动
    settings.assert_production_ready()
    database.init_db(db_url)

    app = FastAPI(title="约饭组队智能Agent系统", version="0.2.0", lifespan=lifespan)

    # CORS：默认 *（仅 H5 开发态需要；小程序端不受 CORS 约束）。
    # prod 下 DP_CORS_ORIGINS 必须为白名单，否则 assert_production_ready 已拒绝启动。
    origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins or ["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for r in (auth.router, users.router, plaza.router, restaurants.router, teams.router,
              chat.router, checkin.router, bills.router, notifications.router,
              reports.router, ws.router):
        app.include_router(r)

    # 上传文件只读托管：文件名由服务端随机生成，目录内不存在可执行内容
    from fastapi.staticfiles import StaticFiles

    from app.core.uploads import upload_root

    app.mount("/uploads", StaticFiles(directory=str(upload_root())), name="uploads")

    @app.exception_handler(IntegrityError)
    async def _integrity_error_handler(request: Request, exc: IntegrityError):
        """DB 约束冲突属于业务冲突，不应以 500 暴露（api.md 的承诺）。"""
        logger.warning("IntegrityError on %s: %s", request.url.path, exc)
        return JSONResponse(
            status_code=409,
            content={"detail": "操作冲突：该资源已被并发修改或状态已变更，请刷新后重试"},
        )

    if settings.ENV != "dev":
        # 非 dev 环境兜底，避免把堆栈泄漏给客户端；
        # dev 环境故意不注册——让异常照常抛出，便于本地与测试定位问题。
        @app.exception_handler(Exception)
        async def _unhandled_handler(request: Request, exc: Exception):
            logger.exception("未处理异常 on %s", request.url.path)
            return JSONResponse(status_code=500, content={"detail": "服务内部错误，请稍后重试"})

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "env": settings.ENV,
            "tz": now_offset_label(),
            "realname_mode": settings.REALNAME_MODE,
            "push_provider": settings.PUSH_PROVIDER,
            "consent_version": settings.CONSENT_VERSION,
        }

    return app


app = create_app()
