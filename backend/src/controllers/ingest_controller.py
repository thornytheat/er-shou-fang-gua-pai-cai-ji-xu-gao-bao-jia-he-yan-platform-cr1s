"""采集运行控制器。"""
from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from src.constants.enums import TriggerKind
from src.services import audit_service, ingest_service
from src.utils.errors import AppError


def list_runs(db: Session, limit: int = 20) -> dict:
    return ingest_service.list_runs(db, limit)


def detail(db: Session, run_id: int) -> dict:
    from src.models.ingest_run import IngestRun

    run = db.get(IngestRun, run_id)
    if run is None:
        raise AppError("NOT_FOUND", 404, detail=f"run_id={run_id}")
    return ingest_service.serialize(run)


def run_batches(db: Session, run_id: int) -> dict:
    from src.models.ingest_run import IngestRun

    run = db.get(IngestRun, run_id)
    if run is None:
        raise AppError("NOT_FOUND", 404, detail=f"run_id={run_id}")
    return {"run_id": run_id, "items": ingest_service.list_batches_by_run(db, run_id)}


def run_ingest(db: Session, source_ids: list[int] | None, trigger: str, principal: dict, request: Request) -> dict:
    kind = trigger if trigger in {item.value for item in TriggerKind} else TriggerKind.MANUAL.value
    run = ingest_service.run_ingest(
        db,
        trigger=kind,
        operator_email=principal["email"],
        source_ids=source_ids,
    )
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="ingest.run",
        entity="ingest_run",
        entity_id=run.id,
        detail={
            "run_no": run.run_no,
            "status": run.status,
            "items": run.items_fetched,
            "throttled": run.throttled_count,
            "created": run.created_count,
            "updated": run.updated_count,
            "clusters": run.cluster_count,
            "flags": run.flag_count,
            "replaced": run.summary.get("replaced_total", 0),
            "isolated": run.summary.get("isolated_total", 0),
            "recomputed": run.summary.get("recomputed", False),
            "source_batches": [
                {
                    "source": batch["source_code"],
                    "status": batch["status"],
                    "received": batch["received_count"],
                    "isolated": batch["isolated_count"],
                    "replaced": batch["replaced_count"],
                    "reason": batch["reason"],
                }
                for batch in run.summary.get("source_batches", [])
            ],
        },
        ip=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(run)
    return ingest_service.serialize(run)
