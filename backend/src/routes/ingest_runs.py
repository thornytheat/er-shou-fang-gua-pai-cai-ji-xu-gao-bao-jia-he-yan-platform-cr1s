from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.constants.roles import INGEST_RUN_ROLES, SOURCE_READ_ROLES
from src.controllers import ingest_controller
from src.middlewares.rbac import require_roles
from src.schemas.ingest import IngestRunIn, IngestRunOut

router = APIRouter(prefix="/ingest-runs", tags=["ingest"])


@router.get("")
def list_runs(
    limit: int = Query(default=20, ge=1, le=100),
    principal: dict = Depends(require_roles(*SOURCE_READ_ROLES)),
    db: Session = Depends(get_db),
) -> dict:
    return ingest_controller.list_runs(db, limit)


@router.post("", response_model=IngestRunOut)
def run_ingest(
    payload: IngestRunIn,
    request: Request,
    principal: dict = Depends(require_roles(*INGEST_RUN_ROLES)),
    db: Session = Depends(get_db),
) -> dict:
    return ingest_controller.run_ingest(db, payload.source_ids, "manual", principal, request)


@router.get("/{run_id}", response_model=IngestRunOut)
def detail(
    run_id: int,
    principal: dict = Depends(require_roles(*SOURCE_READ_ROLES)),
    db: Session = Depends(get_db),
) -> dict:
    return ingest_controller.detail(db, run_id)


@router.get("/{run_id}/batches")
def run_batches(
    run_id: int,
    principal: dict = Depends(require_roles(*SOURCE_READ_ROLES)),
    db: Session = Depends(get_db),
) -> dict:
    """逐源落批明细：每源收到 / 隔离 / 替换多少条及原因。"""
    return ingest_controller.run_batches(db, run_id)
