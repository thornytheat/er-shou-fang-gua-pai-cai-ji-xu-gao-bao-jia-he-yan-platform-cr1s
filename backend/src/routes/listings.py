from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.constants.roles import LISTING_WRITE_ROLES, READ_ROLES
from src.controllers import listing_controller
from src.middlewares.rbac import require_roles
from src.schemas.listing import ListingDetail, ListingPage, PriceFixIn

router = APIRouter(prefix="/listings", tags=["listings"])


@router.get("/options")
def options(
    principal: dict = Depends(require_roles(*READ_ROLES)),
    db: Session = Depends(get_db),
) -> dict:
    return listing_controller.options(db)


@router.get("", response_model=ListingPage)
def list_listings(
    q: str | None = None,
    community: str | None = None,
    layout: str | None = None,
    source_id: int | None = None,
    flag_type: str | None = None,
    duplicate_only: bool = False,
    primary_only: bool = False,
    sort: str = Query(default="unit_price"),
    order: str = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=24, ge=1, le=100),
    principal: dict = Depends(require_roles(*READ_ROLES)),
    db: Session = Depends(get_db),
) -> dict:
    return listing_controller.list_listings(
        db,
        role=principal["role"],
        q=q,
        community=community,
        layout=layout,
        source_id=source_id,
        flag_type=flag_type,
        duplicate_only=duplicate_only,
        primary_only=primary_only,
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
    )


@router.get("/{listing_id}", response_model=ListingDetail)
def detail(
    listing_id: int,
    principal: dict = Depends(require_roles(*READ_ROLES)),
    db: Session = Depends(get_db),
) -> dict:
    return listing_controller.detail(db, listing_id, principal["role"])


@router.patch("/{listing_id}/price", response_model=ListingDetail)
def fix_price(
    listing_id: int,
    payload: PriceFixIn,
    request: Request,
    principal: dict = Depends(require_roles(*LISTING_WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> dict:
    return listing_controller.fix_price(
        db, listing_id, payload.unit_price, payload.note, principal, request
    )
