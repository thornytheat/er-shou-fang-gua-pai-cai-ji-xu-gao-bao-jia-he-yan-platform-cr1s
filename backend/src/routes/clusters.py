from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.constants.roles import CLUSTER_WRITE_ROLES, READ_ROLES
from src.controllers import cluster_controller
from src.middlewares.rbac import require_roles
from src.schemas.cluster import ClusterPage

router = APIRouter(prefix="/clusters", tags=["clusters"])


@router.get("", response_model=ClusterPage)
def list_clusters(
    duplicate_only: bool = True,
    limit: int = 60,
    principal: dict = Depends(require_roles(*READ_ROLES)),
    db: Session = Depends(get_db),
) -> dict:
    return cluster_controller.list_clusters(db, duplicate_only=duplicate_only, limit=limit)


@router.post("/recompute")
def recompute(
    request: Request,
    principal: dict = Depends(require_roles(*CLUSTER_WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> dict:
    return cluster_controller.recompute(db, principal, request)
