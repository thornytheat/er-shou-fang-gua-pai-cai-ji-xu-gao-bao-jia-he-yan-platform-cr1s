"""行情导出控制器。"""
from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from src.services import audit_service, export_service


def preview(db: Session, **filters) -> dict:
    rows = export_service.rows_for_export(db, **filters)
    return {
        "headers": export_service.HEADERS,
        "rows": [dict(zip(export_service.HEADERS, row)) for row in rows[:20]],
        "total_rows": len(rows),
    }


def download(db: Session, principal: dict, request: Request, **filters) -> tuple[str, str, int]:
    content, filename, row_count = export_service.build_csv(db, **filters)
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="export.market",
        entity="export",
        entity_id=None,
        detail={"rows": row_count, "filters": {key: value for key, value in filters.items() if value}},
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return content, filename, row_count
