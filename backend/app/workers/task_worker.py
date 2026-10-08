"""后台 worker：消费 task_queue（副作用 outbox），执行 WS 广播。"""

import asyncio
import json
import logging

from sqlalchemy import select

from app.api.ws import manager
from app.core.timeutil import now as _now
from app.models.task import TaskQueue as TaskQueueRow

logger = logging.getLogger("task_worker")


def _fetch_pending(limit: int = 100):
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        rows = db.execute(
            select(TaskQueueRow).where(TaskQueueRow.status == "pending").limit(limit)
        ).scalars().all()
        return [(r.id, r.kind, r.payload) for r in rows]
    finally:
        db.close()


def _set_status(task_id: int, status: str) -> None:
    """更新任务终态：done（已广播）/ failed（永久性错误，不再重试）"""
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        row = db.get(TaskQueueRow, task_id)
        if row:
            row.status = status
            row.done_at = _now()
            db.commit()
    except Exception:
        db.rollback()
        # 仅在 DB 故障时发生；任务保留 pending，下轮重试
        logger.exception("任务状态更新失败 id=%s -> %s", task_id, status)
    finally:
        db.close()


async def run_worker(poll_interval: float = 0.2):
    while True:
        try:
            tasks = _fetch_pending()
            for tid, kind, payload in tasks:
                if kind == "kick_channel":
                    # 踢人/退队断订：把该用户的连接从队伍频道摘除（同步字典操作，不会失败）
                    try:
                        data = json.loads(payload)
                        removed = manager.unsubscribe_user(
                            data.get("channel", ""), int(data.get("user_id") or 0)
                        )
                        if removed:
                            logger.info("已断订 %s（user=%s，%s 个连接）",
                                        data.get("channel"), data.get("user_id"), removed)
                    except Exception:
                        logger.exception("断订任务执行异常 id=%s，标记 failed", tid)
                    _set_status(tid, "done")
                    continue
                if kind != "broadcast":
                    logger.warning("未知任务类型 %s（id=%s），标记 failed", kind, tid)
                    _set_status(tid, "failed")
                    continue
                try:
                    data = json.loads(payload)
                except ValueError:
                    logger.exception("任务 payload 非法 JSON id=%s，标记 failed", tid)
                    _set_status(tid, "failed")
                    continue
                try:
                    await manager.broadcast(
                        data.get("channel", ""), data.get("event", ""), data.get("data", {})
                    )
                except Exception:
                    # 广播瞬时失败（如事件循环异常）：保留 pending，下轮重试
                    logger.exception("广播执行失败 id=%s，保留 pending 下轮重试", tid)
                    continue
                _set_status(tid, "done")
        except Exception:
            logger.exception("worker 轮询异常")
        await asyncio.sleep(poll_interval)
