"""概览控制器。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from src.services import overview_service


def overview(db: Session) -> dict:
    return overview_service.overview(db)
