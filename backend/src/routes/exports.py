from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.constants.roles import EXPORT_ROLES, READ_ROLES
from src.controllers import export_controller
from src.middlewares.rbac import require_roles

router = APIRouter(prefix="/exports", tags=["exports"])


@router.get("/market-preview")
def preview(
    community: str | None = None,
    since: str | None = None,
    flag_only: bool = False,
    principal: dict = Depends(require_roles(*READ_ROLES)),
    db: Session = Depends(get_db),
) -> dict:
    return export_controller.preview(db, community=community, since=since, flag_only=flag_only)


@router.get("/market.csv")
def download(
    request: Request,
    community: str | None = None,
    since: str | None = None,
    flag_only: bool = False,
    principal: dict = Depends(require_roles(*EXPORT_ROLES)),
    db: Session = Depends(get_db),
) -> Response:
    content, filename, row_count = export_controller.download(
        db, principal, request, community=community, since=since, flag_only=flag_only
    )
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Rentlens-Rows": str(row_count),
        },
    )
