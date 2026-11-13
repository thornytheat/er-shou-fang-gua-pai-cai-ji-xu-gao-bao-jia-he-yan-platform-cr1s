"""顶栏与登录后首屏共用的概览数据。"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.config.settings import settings
from src.models.block_stat import BlockStat
from src.models.cluster import ListingCluster
from src.models.ingest_run import IngestRun
from src.models.listing import Listing
from src.models.price_flag import PriceFlag
from src.models.source import Source
from src.services import flag_service, ingest_service
from src.utils.timeutil import iso_utc, utcnow


def worker_alive() -> bool:
    try:
        import redis

        client = redis.Redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=1)
        value = client.get("rentlens:worker:heartbeat")
        if value:
            import time

            return (time.time() - float(value)) < 120
    except Exception:  # noqa: BLE001 - 心跳读不到就是未知
        return False
    return False


def overview(db: Session) -> dict:
    sources = db.scalar(select(func.count()).select_from(Source)) or 0
    enabled_sources = db.scalar(select(func.count()).select_from(Source).where(Source.enabled.is_(True))) or 0
    listings = db.scalar(select(func.count()).select_from(Listing)) or 0
    quarantined = (
        db.scalar(select(func.count()).select_from(Listing).where(Listing.quarantined.is_(True))) or 0
    )
    primaries = (
        db.scalar(
            select(func.count())
            .select_from(Listing)
            .where(Listing.is_primary.is_(True), Listing.quarantined.is_(False))
        )
        or 0
    )
    duplicate_clusters = (
        db.scalar(select(func.count()).select_from(ListingCluster).where(ListingCluster.member_count > 1)) or 0
    )
    duplicate_members = (
        db.scalar(
            select(func.sum(ListingCluster.member_count)).where(ListingCluster.member_count > 1)
        )
        or 0
    )
    blocks = db.scalars(select(BlockStat).order_by(BlockStat.community, BlockStat.layout)).all()
    latest = ingest_service.latest_run(db)
    flags = flag_service.counts(db)
    return {
        "sources": int(sources),
        "sources_enabled": int(enabled_sources),
        "listings": int(listings),
        "quarantined": int(quarantined),
        "primaries": int(primaries),
        "duplicate_clusters": int(duplicate_clusters),
        "duplicate_members": int(duplicate_members or 0),
        "flags": flags,
        "blocks": [
            {
                "block_key": row.block_key,
                "community": row.community,
                "layout": row.layout,
                "all_count": row.all_count,
                "primary_count": row.primary_count,
                "unknown_count": row.unknown_count,
                "naive_mean": row.naive_mean,
                "dedup_mean": row.dedup_mean,
                "median_price": row.median_price,
                "mad": row.mad,
                "inflation_pct": round((row.naive_mean - row.dedup_mean) / row.dedup_mean * 100, 2)
                if row.naive_mean and row.dedup_mean
                else None,
            }
            for row in blocks
        ],
        "latest_run": ingest_service.serialize(latest) if latest else None,
        "worker_alive": worker_alive(),
        "server_time": iso_utc(utcnow()),
    }
