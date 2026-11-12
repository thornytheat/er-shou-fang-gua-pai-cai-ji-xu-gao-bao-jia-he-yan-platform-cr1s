from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.controllers import overview_controller
from src.middlewares.rbac import principal_of

router = APIRouter(tags=["overview"])


@router.get("/overview")
def overview(request: Request, principal: dict = Depends(principal_of), db: Session = Depends(get_db)) -> dict:
    return overview_controller.overview(db)
