from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.constants.roles import AUDIT_ROLES
from src.middlewares.rbac import require_roles
from src.services import audit_service

router = APIRouter(prefix="/audit-logs", tags=["audit"])


@router.get("")
def list_logs(
    limit: int = Query(default=60, ge=1, le=200),
    principal: dict = Depends(require_roles(*AUDIT_ROLES)),
    db: Session = Depends(get_db),
) -> dict:
    return audit_service.list_logs(db, limit)
