"""采集源：列表 / 修改 / 新建 + 每个源的挂牌量。"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.constants.enums import PLATFORM_LABELS, PlatformKind
from src.models.listing import Listing
from src.models.source import Source
from src.utils.errors import AppError
from src.utils.timeutil import iso_utc, utcnow


def serialize(source: Source, listing_count: int = 0, latest_batch: dict | None = None) -> dict:
    return {
        "id": source.id,
        "code": source.code,
        "name": source.name,
        "platform": source.platform,
        "platform_label": PLATFORM_LABELS.get(source.platform, source.platform),
        "base_url": source.base_url,
        "frequency": source.frequency,
        "rate_limit_per_min": source.rate_limit_per_min,
        "page_size": source.page_size,
        "enabled": bool(source.enabled),
        "last_run_at": iso_utc(source.last_run_at),
        "last_run_status": source.last_run_status,
        "last_run_items": source.last_run_items,
        "listing_count": listing_count,
        "note": source.note,
        "latest_batch": latest_batch,
    }


def list_sources(db: Session, include_disabled: bool = True) -> dict:
    from src.services.ingest_service import latest_batches

    query = select(Source).order_by(Source.sort_order, Source.id)
    if not include_disabled:
        query = query.where(Source.enabled.is_(True))
    sources = db.scalars(query).all()
    counts = dict(
        db.execute(select(Listing.source_id, func.count()).group_by(Listing.source_id)).all()
    )
    batch_by_source = {batch["source_id"]: batch for batch in latest_batches(db)}
    return {
        "items": [
            serialize(
                source,
                int(counts.get(source.id, 0)),
                batch_by_source.get(source.id),
            )
            for source in sources
        ]
    }


def get_source(db: Session, source_id: int) -> Source:
    source = db.get(Source, source_id)
    if source is None:
        raise AppError("NOT_FOUND", 404, detail=f"source_id={source_id}")
    return source


def update_source(db: Session, source_id: int, payload: dict) -> Source:
    source = get_source(db, source_id)
    for field in ("frequency", "rate_limit_per_min", "page_size", "enabled", "note"):
        if payload.get(field) is not None:
            setattr(source, field, payload[field])
    source.updated_at = utcnow()
    db.flush()
    return source


def create_source(db: Session, payload: dict) -> Source:
    exists = db.scalar(select(Source).where(Source.code == payload["code"]))
    if exists is not None:
        raise AppError("CONFLICT", 409, detail=f"code={payload['code']} 已存在")
    if payload["platform"] not in {item.value for item in PlatformKind}:
        raise AppError("VALIDATION", 422, detail="platform 不在枚举内")
    source = Source(
        code=payload["code"],
        name=payload["name"],
        platform=payload["platform"],
        base_url=payload["base_url"],
        frequency=payload["frequency"],
        rate_limit_per_min=payload["rate_limit_per_min"],
        page_size=payload["page_size"],
        note=payload.get("note"),
        sort_order=99,
    )
    db.add(source)
    db.flush()
    return source
