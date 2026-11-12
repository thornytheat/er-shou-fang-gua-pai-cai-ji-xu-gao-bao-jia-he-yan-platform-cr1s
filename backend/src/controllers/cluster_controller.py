"""去重簇控制器。"""
from __future__ import annotations

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.models.cluster import ListingCluster
from src.models.listing import Listing
from src.services import audit_service, cluster_service, listing_service
from src.utils.timeutil import iso_date


def list_clusters(db: Session, duplicate_only: bool = True, limit: int = 60) -> dict:
    query = select(ListingCluster)
    if duplicate_only:
        query = query.where(ListingCluster.member_count > 1)
    query = query.order_by(ListingCluster.member_count.desc(), ListingCluster.id.asc()).limit(limit)
    rows = db.scalars(query).all()
    total = db.scalar(select(func.count()).select_from(ListingCluster)) or 0
    duplicate_total = (
        db.scalar(select(func.count()).select_from(ListingCluster).where(ListingCluster.member_count > 1)) or 0
    )
    listing_map = {row.id: row for row in db.scalars(select(Listing)).all()}
    items = []
    for cluster in rows:
        primary = listing_map.get(cluster.primary_listing_id)
        items.append(
            {
                "id": cluster.id,
                "community": cluster.community,
                "layout": cluster.layout,
                "block_key": cluster.block_key,
                "primary_listing_id": cluster.primary_listing_id,
                "member_count": cluster.member_count,
                "platform_count": cluster.platform_count,
                "avg_unit_price": cluster.avg_unit_price,
                "min_similarity": cluster.min_similarity,
                "max_similarity": cluster.max_similarity,
                "spread_pct": cluster.spread_pct,
                "primary_title": primary.title if primary else None,
                "primary_list_date": iso_date(primary.list_date) if primary else None,
            }
        )
    return {
        "items": items,
        "total": int(total),
        "duplicate_total": int(duplicate_total),
        "dedup_total": int(total),
    }


def recompute(db: Session, principal: dict, request: Request) -> dict:
    result = cluster_service.recompute(db)
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="cluster.recompute",
        entity="cluster",
        entity_id=None,
        detail={
            "clusters": result["cluster_count"],
            "duplicates": result["duplicate_count"],
            "dedup": result["dedup_count"],
            "flags": result["flag_total"],
        },
        ip=request.client.host if request.client else None,
    )
    db.commit()
    overview = listing_service.filter_options(db)
    return {"result": result, "pending_reviews": overview["pending_reviews"]}
