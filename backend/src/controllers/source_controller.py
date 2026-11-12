"""采集源控制器。"""
from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from src.config.database import SessionLocal
from src.services import audit_service, ingest_service, source_service
from src.utils.errors import AppError


def list_sources(db: Session) -> dict:
    return source_service.list_sources(db)


def update_source(db: Session, source_id: int, payload: dict, principal: dict, request: Request) -> dict:
    source = source_service.update_source(db, source_id, payload)
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="source.update",
        entity="source",
        entity_id=source.id,
        detail={key: value for key, value in payload.items() if value is not None},
        ip=request.client.host if request.client else None,
    )
    counts = source_service.list_sources(db)["items"]
    db.commit()
    match = next((row for row in counts if row["id"] == source.id), None)
    return match or source_service.serialize(source)


def create_source(db: Session, payload: dict, principal: dict, request: Request) -> dict:
    source = source_service.create_source(db, payload)
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="source.create",
        entity="source",
        entity_id=source.id,
        detail={"code": source.code, "platform": source.platform},
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return source_service.serialize(source)


def run_source(db: Session, source_id: int, principal: dict, request: Request) -> dict:
    source = source_service.get_source(db, source_id)
    if not source.enabled:
        raise AppError("SOURCE_DISABLED", 409, detail={"code": source.code})
    run = ingest_service.run_ingest(
        db,
        trigger="manual",
        operator_email=principal["email"],
        source_ids=[source_id],
    )
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="ingest.run",
        entity="source",
        entity_id=source.id,
        detail={"run_no": run.run_no, "items": run.items_fetched, "scope": "single"},
        ip=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(run)
    return ingest_service.serialize(run)
