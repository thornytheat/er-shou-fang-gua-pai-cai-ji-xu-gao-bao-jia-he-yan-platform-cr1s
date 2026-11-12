from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.constants.roles import READ_ROLES, REVIEW_ROLES
from src.controllers import flag_controller
from src.middlewares.rbac import require_roles
from src.schemas.price_flag import PriceFlagPage, ReviewIn

router = APIRouter(prefix="/flags", tags=["flags"])


@router.get("", response_model=PriceFlagPage)
def list_flags(
    flag_type: str | None = None,
    review_status: str | None = None,
    limit: int = 60,
    principal: dict = Depends(require_roles(*READ_ROLES)),
    db: Session = Depends(get_db),
) -> dict:
    return flag_controller.list_flags(db, flag_type=flag_type, review_status=review_status, limit=limit)


@router.get("/summary")
def summary(
    principal: dict = Depends(require_roles(*READ_ROLES)),
    db: Session = Depends(get_db),
) -> dict:
    return flag_controller.summary(db)


@router.post("/detect")
def detect(
    request: Request,
    principal: dict = Depends(require_roles(*REVIEW_ROLES)),
    db: Session = Depends(get_db),
) -> dict:
    return flag_controller.detect(db, principal, request)


@router.patch("/{flag_id}")
def review(
    flag_id: int,
    payload: ReviewIn,
    request: Request,
    principal: dict = Depends(require_roles(*REVIEW_ROLES)),
    db: Session = Depends(get_db),
) -> dict:
    return flag_controller.review(db, flag_id, payload.review_status, payload.note, principal, request)
