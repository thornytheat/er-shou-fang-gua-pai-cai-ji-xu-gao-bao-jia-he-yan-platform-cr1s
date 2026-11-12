"""挂牌池控制器。"""
from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from src.services import audit_service, cluster_service, listing_service


def list_listings(db: Session, role: str, **filters) -> dict:
    return listing_service.list_listings(db, role=role, **filters)


def detail(db: Session, listing_id: int, role: str) -> dict:
    return listing_service.get_listing(db, listing_id, role)


def fix_price(db: Session, listing_id: int, unit_price: int, note: str, principal: dict, request: Request) -> dict:
    before = listing_service.get_listing(db, listing_id, principal["role"])
    previous = before["listing"]["unit_price"]
    listing_service.fix_price(db, listing_id, unit_price, note)
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="listing.price_fix",
        entity="listing",
        entity_id=listing_id,
        detail={"from": previous, "to": unit_price, "note": note},
        ip=request.client.host if request.client else None,
    )
    db.commit()
    # 单价变化会影响中位/MAD，立刻重算该批次的簇与价格工单
    cluster_service.recompute(db)
    db.commit()
    return listing_service.get_listing(db, listing_id, principal["role"])


def options(db: Session) -> dict:
    return listing_service.filter_options(db)
