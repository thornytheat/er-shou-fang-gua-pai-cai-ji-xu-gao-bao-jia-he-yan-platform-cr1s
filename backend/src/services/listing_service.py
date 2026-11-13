"""挂牌池与房源详情（含多平台并排、价格序列、簇内相似度）。"""
from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from src.constants.enums import FLAG_TYPE_LABELS, REVIEW_LABELS, ReviewStatus
from src.constants.roles import can_see_contact
from src.models.block_stat import BlockStat
from src.models.cluster import ListingCluster
from src.models.listing import Listing
from src.models.price_flag import PriceFlag
from src.models.source import Source
from src.services import cluster_service
from src.utils.errors import AppError
from src.utils.timeutil import iso_date, iso_utc, utcnow

SORT_FIELDS = {"unit_price", "total_price_wan", "list_date", "area_sqm", "id"}


def _flag_map(db: Session) -> dict[int, PriceFlag]:
    return {flag.listing_id: flag for flag in db.scalars(select(PriceFlag)).all()}


def _cluster_map(db: Session) -> dict[int, ListingCluster]:
    return {cluster.id: cluster for cluster in db.scalars(select(ListingCluster)).all()}


def _source_map(db: Session) -> dict[int, Source]:
    return {source.id: source for source in db.scalars(select(Source)).all()}


def serialize_row(
    listing: Listing,
    *,
    source: Source | None,
    cluster: ListingCluster | None,
    flag: PriceFlag | None,
    role: str,
) -> dict:
    flag_type = flag.flag_type if flag else None
    return {
        "id": listing.id,
        "source_id": listing.source_id,
        "source_name": source.name if source else "未知来源",
        "source_platform": source.platform if source else "",
        "source_listing_no": listing.source_listing_no,
        "community": listing.community,
        "layout": listing.layout,
        "area_sqm": listing.area_sqm,
        "floor": listing.floor,
        "total_floors": listing.total_floors,
        "floor_band": listing.floor_band,
        "unit_price": listing.unit_price,
        "total_price_wan": listing.total_price_wan,
        "list_date": iso_date(listing.list_date),
        "title": listing.title,
        "agent_name": listing.agent_name,
        "agent_contact": listing.agent_contact if can_see_contact(role) else None,
        "completeness": listing.completeness,
        "cluster_id": listing.cluster_id,
        "cluster_size": cluster.member_count if cluster else 1,
        "platform_count": cluster.platform_count if cluster else 1,
        "is_primary": bool(listing.is_primary),
        "quarantined": bool(listing.quarantined),
        "flag_type": flag_type,
        "flag_label": FLAG_TYPE_LABELS.get(flag_type) if flag_type else None,
        "deviation_pct": flag.deviation_pct if flag else None,
        "review_status": flag.review_status if flag else None,
    }


def list_listings(
    db: Session,
    *,
    role: str,
    q: str | None = None,
    community: str | None = None,
    layout: str | None = None,
    source_id: int | None = None,
    flag_type: str | None = None,
    duplicate_only: bool = False,
    primary_only: bool = False,
    sort: str = "unit_price",
    order: str = "desc",
    page: int = 1,
    page_size: int = 24,
) -> dict:
    query = select(Listing)
    if q:
        pattern = f"%{q.strip()}%"
        query = query.where(or_(Listing.title.like(pattern), Listing.community.like(pattern)))
    if community:
        query = query.where(Listing.community == community)
    if layout:
        query = query.where(Listing.layout == layout)
    if source_id:
        query = query.where(Listing.source_id == source_id)
    if primary_only:
        query = query.where(Listing.is_primary.is_(True))
    if duplicate_only:
        subquery = select(ListingCluster.id).where(ListingCluster.member_count > 1)
        query = query.where(Listing.cluster_id.in_(subquery))
    if flag_type:
        subquery = select(PriceFlag.listing_id).where(PriceFlag.flag_type == flag_type)
        query = query.where(Listing.id.in_(subquery))

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    field = sort if sort in SORT_FIELDS else "unit_price"
    column = getattr(Listing, field)
    query = query.order_by(column.desc() if order == "desc" else column.asc(), Listing.id.asc())
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    rows = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()

    sources = _source_map(db)
    clusters = _cluster_map(db)
    flags = _flag_map(db)
    items = [
        serialize_row(
            listing,
            source=sources.get(listing.source_id),
            cluster=clusters.get(listing.cluster_id) if listing.cluster_id else None,
            flag=flags.get(listing.id),
            role=role,
        )
        for listing in rows
    ]
    # 页内均价/区间只统计有效挂牌；整源隔离的挂牌可被看到但不进任何统计
    blocked = [row for row in items if row["unit_price"] is None]
    priced = [row for row in items if row["unit_price"] is not None and not row["quarantined"]]
    sums = {
        "page_avg_unit_price": round(sum(row["unit_price"] for row in priced) / len(priced)) if priced else None,
        "page_min_unit_price": min((row["unit_price"] for row in priced), default=None),
        "page_max_unit_price": max((row["unit_price"] for row in priced), default=None),
        "unknown_area": len(blocked),
        "duplicate_rows": sum(1 for row in items if row["cluster_size"] > 1),
        "quarantined_rows": sum(1 for row in items if row["quarantined"]),
    }
    return {"items": items, "total": total, "page": page, "page_size": page_size, "sums": sums}


def get_listing(db: Session, listing_id: int, role: str) -> dict:
    listing = db.get(Listing, listing_id)
    if listing is None:
        raise AppError("NOT_FOUND", 404, detail=f"listing_id={listing_id}")
    sources = _source_map(db)
    flags = _flag_map(db)
    cluster = db.get(ListingCluster, listing.cluster_id) if listing.cluster_id else None
    flag = flags.get(listing.id)
    base = serialize_row(
        listing, source=sources.get(listing.source_id), cluster=cluster, flag=flag, role=role
    )

    members: list[dict] = []
    if cluster is not None:
        member_rows = db.scalars(select(Listing).where(Listing.cluster_id == cluster.id)).all()
        for member in sorted(member_rows, key=lambda row: (iso_date(row.list_date) or "", row.id)):
            members.append(
                {
                    "id": member.id,
                    "source_name": sources[member.source_id].name if member.source_id in sources else "未知来源",
                    "source_platform": sources[member.source_id].platform if member.source_id in sources else "",
                    "source_listing_no": member.source_listing_no,
                    "unit_price": member.unit_price,
                    "total_price_wan": member.total_price_wan,
                    "list_date": iso_date(member.list_date),
                    "title": member.title,
                    "floor": member.floor,
                    "floor_band": member.floor_band,
                    "similarity": cluster_service.similarity_for(db, cluster.id, member.id),
                    "is_primary": bool(member.is_primary),
                }
            )

    stat = db.scalar(
        select(BlockStat).where(BlockStat.block_key == f"{listing.community}::{listing.layout}")
    )
    block = (
        {
            "block_key": stat.block_key,
            "community": stat.community,
            "layout": stat.layout,
            "all_count": stat.all_count,
            "primary_count": stat.primary_count,
            "unknown_count": stat.unknown_count,
            "naive_mean": stat.naive_mean,
            "dedup_mean": stat.dedup_mean,
            "median_price": stat.median_price,
            "mad": stat.mad,
            "min_price": stat.min_price,
            "max_price": stat.max_price,
            "inflation_pct": round((stat.naive_mean - stat.dedup_mean) / stat.dedup_mean * 100, 2)
            if stat.naive_mean and stat.dedup_mean
            else None,
            "updated_at": iso_utc(stat.updated_at),
        }
        if stat
        else {}
    )

    flag_payload = (
        {
            "id": flag.id,
            "flag_type": flag.flag_type,
            "flag_label": FLAG_TYPE_LABELS.get(flag.flag_type, flag.flag_type),
            "unit_price": flag.unit_price,
            "median_price": flag.median_price,
            "deviation_pct": flag.deviation_pct,
            "z_score": flag.z_score,
            "confidence": flag.confidence,
            "sample_size": flag.sample_size,
            "review_status": flag.review_status,
            "review_label": REVIEW_LABELS.get(flag.review_status, flag.review_status),
            "review_note": flag.review_note,
            "reviewed_by": flag.reviewed_by,
            "reviewed_at": iso_utc(flag.reviewed_at),
        }
        if flag
        else None
    )

    series = [
        {
            "date": member["list_date"],
            "unit_price": member["unit_price"],
            "source_name": member["source_name"],
            "label": member["source_listing_no"],
            "is_primary": member["is_primary"],
        }
        for member in members
        if member["unit_price"]
    ]
    return {
        "listing": base,
        "members": members,
        "block": block,
        "flag": flag_payload,
        "price_series": series,
    }


def fix_price(db: Session, listing_id: int, unit_price: int, note: str) -> Listing:
    listing = db.get(Listing, listing_id)
    if listing is None:
        raise AppError("NOT_FOUND", 404, detail=f"listing_id={listing_id}")
    if listing.quarantined:
        raise AppError(
            "SOURCE_QUARANTINED",
            409,
            detail={"listing_id": listing_id, "message": "该挂牌所属来源已整源隔离，恢复完整采集前不能改价"},
        )
    listing.unit_price = int(unit_price)
    if listing.area_sqm:
        listing.total_price_wan = round(unit_price * listing.area_sqm / 10000, 2)
    listing.updated_at = utcnow()
    db.flush()
    return listing


def filter_options(db: Session) -> dict:
    communities = [row[0] for row in db.execute(select(Listing.community).distinct().order_by(Listing.community))]
    layouts = [row[0] for row in db.execute(select(Listing.layout).distinct().order_by(Listing.layout))]
    sources = db.scalars(select(Source).order_by(Source.sort_order)).all()
    return {
        "communities": communities,
        "layouts": layouts,
        "sources": [{"id": source.id, "name": source.name, "platform": source.platform} for source in sources],
        "pending_reviews": len(
            db.scalars(
                select(PriceFlag)
                .join(Listing, Listing.id == PriceFlag.listing_id)
                .where(
                    PriceFlag.review_status == ReviewStatus.PENDING.value,
                    Listing.quarantined.is_(False),
                )
            ).all()
        ),
    }
