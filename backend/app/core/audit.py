"""审计日志写入助手。

审计发现：踢人 / 改账单 / 解散 / 实名 / 注销这些敏感动作在库里没有任何留痕，
纠纷复盘与风控取证无从下手。本模块提供统一入口，**只追加不修改**。

注意：必须在调用方的事务内使用（不自行 commit），保证与业务变更同生共死。
"""

import json

from sqlalchemy.orm import Session

from app.models.audit import AuditLog

SENSITIVE_KEYS = {"password", "id_card", "real_name", "username", "token", "secret"}


def _scrub(value):
    """递归脱敏：敏感键一律替换为 ***，避免审计表本身变成新的泄漏面。"""
    if isinstance(value, dict):
        return {
            k: ("***" if k.lower() in SENSITIVE_KEYS else _scrub(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def audit(db: Session, actor_id: int | None, action: str,
          target_type: str | None = None, target_id: int | None = None,
          **detail) -> None:
    """落一条审计日志（同事务）。"""
    db.add(
        AuditLog(
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            detail=json.dumps(_scrub(detail), ensure_ascii=False, default=str),
        )
    )
