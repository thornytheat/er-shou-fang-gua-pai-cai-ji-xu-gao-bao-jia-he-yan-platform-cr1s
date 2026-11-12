"""价格工单控制器。"""
from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from src.services import audit_service, cluster_service, flag_service


def list_flags(db: Session, **filters) -> dict:
    return flag_service.list_flags(db, **filters)


def review(db: Session, flag_id: int, review_status: str, note: str | None, principal: dict, request: Request) -> dict:
    flag = flag_service.review(db, flag_id, review_status, note, principal["email"])
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="flag.review",
        entity="price_flag",
        entity_id=flag.id,
        detail={
            "flag_type": flag.flag_type,
            "review_status": review_status,
            "deviation_pct": flag.deviation_pct,
            "z": flag.z_score,
            "note": note,
        },
        ip=request.client.host if request.client else None,
    )
    db.commit()
    payload = flag_service.list_flags(db, limit=200)
    for item in payload["items"]:
        if item["id"] == flag_id:
            return item
    return {"id": flag_id}


def detect(db: Session, principal: dict, request: Request) -> dict:
    result = cluster_service.recompute(db)
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="flag.detect",
        entity="price_flag",
        entity_id=None,
        detail=result["flag_counts"],
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return {"result": result, "counts": flag_service.counts(db)}


def summary(db: Session) -> dict:
    return flag_service.counts(db)
