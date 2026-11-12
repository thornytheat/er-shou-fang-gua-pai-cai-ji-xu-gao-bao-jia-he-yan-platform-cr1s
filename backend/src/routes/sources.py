from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.constants.roles import INGEST_RUN_ROLES, SOURCE_READ_ROLES, SOURCE_WRITE_ROLES
from src.controllers import source_controller
from src.middlewares.rbac import require_roles
from src.schemas.source import SourceCreateIn, SourcePatchIn

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("")
def list_sources(
    principal: dict = Depends(require_roles(*SOURCE_READ_ROLES)),
    db: Session = Depends(get_db),
) -> dict:
    return source_controller.list_sources(db)


@router.post("")
def create_source(
    payload: SourceCreateIn,
    request: Request,
    principal: dict = Depends(require_roles(*SOURCE_WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> dict:
    return source_controller.create_source(db, payload.model_dump(), principal, request)


@router.patch("/{source_id}")
def update_source(
    source_id: int,
    payload: SourcePatchIn,
    request: Request,
    principal: dict = Depends(require_roles(*SOURCE_WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> dict:
    return source_controller.update_source(db, source_id, payload.model_dump(), principal, request)


@router.post("/{source_id}/run")
def run_source(
    source_id: int,
    request: Request,
    principal: dict = Depends(require_roles(*INGEST_RUN_ROLES)),
    db: Session = Depends(get_db),
) -> dict:
    return source_controller.run_source(db, source_id, principal, request)
