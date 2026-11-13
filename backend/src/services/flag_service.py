"""核验队列：列表 / 复核 / 统计。"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.constants.enums import (
    FLAG_TYPE_LABELS,
    FLAG_TYPE_ORDER,
    REVIEW_LABELS,
    ReviewStatus,
)
from src.models.listing import Listing
from src.models.price_flag import PriceFlag
from src.models.source import Source
from src.utils.errors import AppError
from src.utils.timeutil import iso_date, iso_utc, utcnow


def counts(db: Session) -> dict:
    # 隔离挂牌的工单不进核验队列（人工复核结果保留，源恢复后重新生效）
    visible = select(PriceFlag.id).join(Listing, Listing.id == PriceFlag.listing_id).where(
        Listing.quarantined.is_(False)
    )
    visible_flags = db.scalars(select(PriceFlag).where(PriceFlag.id.in_(visible))).all()
    by_type: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for flag in visible_flags:
        by_type[flag.flag_type] = by_type.get(flag.flag_type, 0) + 1
        by_status[flag.review_status] = by_status.get(flag.review_status, 0) + 1
    total = len(visible_flags)
    return {
        "total": int(total),
        "by_type": {key: int(by_type.get(key, 0)) for key in FLAG_TYPE_ORDER},
        "by_status": {
            ReviewStatus.PENDING.value: int(by_status.get(ReviewStatus.PENDING.value, 0)),
            ReviewStatus.CONFIRMED.value: int(by_status.get(ReviewStatus.CONFIRMED.value, 0)),
            ReviewStatus.DISMISSED.value: int(by_status.get(ReviewStatus.DISMISSED.value, 0)),
        },
    }


def list_flags(
    db: Session,
    *,
    flag_type: str | None = None,
    review_status: str | None = None,
    limit: int = 60,
) -> dict:
    query = (
        select(PriceFlag)
        .join(Listing, Listing.id == PriceFlag.listing_id)
        .where(Listing.quarantined.is_(False))
    )
    if flag_type:
        query = query.where(PriceFlag.flag_type == flag_type)
    if review_status:
        query = query.where(PriceFlag.review_status == review_status)
    query = query.order_by(PriceFlag.flag_type.asc(), PriceFlag.confidence.desc())
    rows = db.scalars(query.limit(limit)).all()
    sources = {source.id: source for source in db.scalars(select(Source)).all()}
    items = []
    for flag in rows:
        listing = db.get(Listing, flag.listing_id)
        items.append(
            {
                "id": flag.id,
                "listing_id": flag.listing_id,
                "cluster_id": flag.cluster_id,
                "flag_type": flag.flag_type,
                "flag_label": FLAG_TYPE_LABELS.get(flag.flag_type, flag.flag_type),
                "community": flag.community,
                "layout": flag.layout,
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
                "detected_at": iso_utc(flag.detected_at),
                "title": listing.title if listing else None,
                "area_sqm": listing.area_sqm if listing else None,
                "list_date": iso_date(listing.list_date) if listing else None,
                "source_name": sources[listing.source_id].name if listing and listing.source_id in sources else None,
            }
        )
    return {"items": items, "total": len(items), "counts": counts(db)}


def review(db: Session, flag_id: int, review_status: str, note: str | None, actor_email: str) -> PriceFlag:
    flag = db.get(PriceFlag, flag_id)
    if flag is None:
        raise AppError("NOT_FOUND", 404, detail=f"flag_id={flag_id}")
    listing = db.get(Listing, flag.listing_id)
    if listing is not None and listing.quarantined:
        # 整源隔离期间禁止复核：这批挂牌已不参与均价/工单，避免人工结论挂到漂移数据上
        raise AppError(
            "SOURCE_QUARANTINED",
            409,
            detail={"listing_id": flag.listing_id, "message": "所属来源已整源隔离，恢复完整采集后才能复核"},
        )
    if review_status not in {item.value for item in ReviewStatus}:
        raise AppError("VALIDATION", 422, detail="review_status 不在枚举内")
    flag.review_status = review_status
    flag.review_note = note
    flag.reviewed_by = actor_email
    flag.reviewed_at = utcnow() if review_status != ReviewStatus.PENDING.value else None
    db.flush()
    return flag
