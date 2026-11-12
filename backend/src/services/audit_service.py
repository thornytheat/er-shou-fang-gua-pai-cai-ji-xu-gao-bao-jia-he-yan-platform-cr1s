"""审计日志：领域层记录 + 查询。"""
from __future__ import annotations

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from src.constants.log_templates import ACTIONS
from src.models.audit import AuditLog
from src.utils.timeutil import iso_utc


def record(
    db: Session,
    actor_email: str,
    actor_role: str,
    action: str,
    entity: str,
    entity_id: str | int | None = None,
    detail: dict | None = None,
    layer: str = "domain",
    ip: str | None = None,
    seed_key: str | None = None,
) -> AuditLog:
    log = AuditLog(
        actor_email=actor_email,
        actor_role=actor_role,
        action=action,
        entity=entity,
        entity_id=str(entity_id) if entity_id is not None else None,
        detail=detail or {},
        layer=layer,
        ip=ip,
        seed_key=seed_key,
    )
    db.add(log)
    return log


def list_logs(db: Session, limit: int = 80) -> dict:
    total = db.scalar(select(func.count()).select_from(AuditLog)) or 0
    rows = db.scalars(select(AuditLog).order_by(desc(AuditLog.id)).limit(limit)).all()
    return {
        "items": [
            {
                "id": row.id,
                "actor_email": row.actor_email,
                "actor_role": row.actor_role,
                "action": row.action,
                "action_label": ACTIONS.get(row.action, row.action),
                "entity": row.entity,
                "entity_id": row.entity_id,
                "detail": row.detail,
                "layer": row.layer,
                "created_at": iso_utc(row.created_at),
            }
            for row in rows
        ],
        "total": total,
    }
