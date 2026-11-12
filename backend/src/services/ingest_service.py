"""采集编排：源 → 页面 → 解析 → 落库 → 去重 → 均价刷新 → 价格核验。

一次运行的副作用全部幂等：挂牌按 (source_id, source_listing_no) upsert，
去重簇按主房源 id upsert，价格工单按 listing_id upsert 且保留人工复核态。
"""
from __future__ import annotations

import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.constants.enums import IngestStatus, ReviewStatus, TriggerKind
from src.constants.limits import MAX_ITEMS_PER_RUN
from src.models.block_stat import BlockStat
from src.models.ingest_run import IngestRun
from src.models.listing import Listing
from src.models.price_flag import PriceFlag
from src.models.source import Source
from src.services import cluster_service, fetch_service
from src.utils.errors import AppError
from src.utils.logger import get_logger
from src.utils.timeutil import iso_utc, utcnow

logger = get_logger("ingest")


def _next_run_no(db: Session) -> str:
    stamp = utcnow().strftime("%Y%m%d%H%M%S")
    seq = len(db.scalars(select(IngestRun.id)).all()) + 1
    return f"RUN-{stamp}-{seq:02d}"


def assert_not_running(db: Session) -> None:
    running = db.scalar(select(IngestRun).where(IngestRun.status == IngestStatus.RUNNING.value))
    if running is not None:
        raise AppError("INGEST_RUNNING", 409, detail={"run_no": running.run_no})


def _upsert_listings(db: Session, rows: list[dict], sources: dict[str, Source]) -> tuple[int, int]:
    created = 0
    updated = 0
    for row in rows[:MAX_ITEMS_PER_RUN]:
        source = sources.get(row["source_code"])
        if source is None:
            continue
        listing = db.scalar(
            select(Listing).where(
                Listing.source_id == source.id,
                Listing.source_listing_no == row["source_listing_no"],
            )
        )
        from datetime import date

        list_date = date.fromisoformat(row["list_date"]) if row.get("list_date") else None
        if listing is None:
            listing = Listing(
                source_id=source.id,
                source_listing_no=row["source_listing_no"],
                community=row["community"],
                layout=row["layout"],
            )
            db.add(listing)
            created += 1
        else:
            updated += 1
        listing.community = row["community"]
        listing.layout = row["layout"]
        listing.area_sqm = row.get("area_sqm")
        listing.floor = row.get("floor")
        listing.total_floors = row.get("total_floors")
        listing.floor_band = row.get("floor_band")
        listing.unit_price = row.get("unit_price")
        listing.total_price_wan = row.get("total_price_wan")
        listing.list_date = list_date
        listing.title = row.get("title") or ""
        listing.agent_name = row.get("agent_name")
        listing.agent_contact = row.get("agent_contact")
        listing.completeness = row.get("completeness") or 0.0
        listing.raw = row.get("raw_json")
    db.flush()
    return created, updated


def _price_refresh_summary(db: Session) -> list[dict]:
    rows = db.scalars(select(BlockStat).order_by(BlockStat.community, BlockStat.layout)).all()
    return [
        {
            "community": row.community,
            "layout": row.layout,
            "primary_count": row.primary_count,
            "all_count": row.all_count,
            "naive_mean": row.naive_mean,
            "dedup_mean": row.dedup_mean,
            "median_price": row.median_price,
            "mad": row.mad,
        }
        for row in rows
    ]


def run_ingest(
    db: Session,
    *,
    trigger: str = TriggerKind.MANUAL.value,
    operator_email: str = "system",
    source_ids: list[int] | None = None,
) -> IngestRun:
    started = time.time()
    assert_not_running(db)
    sources = db.scalars(select(Source).order_by(Source.sort_order, Source.id)).all()
    if source_ids:
        sources = [source for source in sources if source.id in set(source_ids)]
    enabled = [source for source in sources if source.enabled]
    if not enabled:
        raise AppError("SOURCE_DISABLED", 409, detail="没有启用的采集源")

    run = IngestRun(
        run_no=_next_run_no(db),
        trigger_kind=trigger,
        status=IngestStatus.RUNNING.value,
        sources_total=len(enabled),
        operator_email=operator_email,
        started_at=utcnow(),
    )
    db.add(run)
    db.flush()

    platforms = fetch_service.load_platforms()
    source_map = {source.code: source for source in enabled}
    all_rows: list[dict] = []
    pages = items = throttled = backoff = 0
    failures: list[str] = []
    throttle_log: list[dict] = []

    for source in enabled:
        try:
            outcome = fetch_service.crawl_source(
                {"code": source.code, "name": source.name}, platforms
            )
        except Exception as exc:  # noqa: BLE001 - 单个源失败不阻塞其它源
            logger.warning("[ingest] %s failed: %s", source.code, exc)
            failures.append(f"{source.code}: {exc}")
            source.last_run_status = IngestStatus.FAILED.value
            source.last_run_at = utcnow()
            continue
        pages += outcome["pages_fetched"]
        items += outcome["items_fetched"]
        throttled += outcome["throttled"]
        backoff += outcome["backoff_ms"]
        throttle_log.extend(
            {"source": source.code, **entry} for entry in outcome["throttle_log"]
        )
        all_rows.extend(outcome["rows"])
        source.last_run_status = IngestStatus.SUCCESS.value
        source.last_run_at = utcnow()
        source.last_run_items = outcome["items_fetched"]

    created, updated = _upsert_listings(db, all_rows, source_map)
    recomputed = cluster_service.recompute(db)
    blocks = _price_refresh_summary(db)

    run.pages_fetched = pages
    run.items_fetched = items
    run.throttled_count = throttled
    run.backoff_ms = backoff
    run.created_count = created
    run.updated_count = updated
    run.cluster_count = recomputed["cluster_count"]
    run.duplicate_count = recomputed["duplicate_count"]
    run.dedup_count = recomputed["dedup_count"]
    run.flag_count = recomputed["flag_total"]
    run.duration_ms = int((time.time() - started) * 1000)
    run.finished_at = utcnow()
    run.status = IngestStatus.PARTIAL.value if failures else IngestStatus.SUCCESS.value
    run.message = "；".join(failures) if failures else "采集、去重、均价刷新与价格核验全部完成"
    run.summary = {
        "throttle_log": throttle_log,
        "flag_counts": recomputed["flag_counts"],
        "blocks": blocks,
        "pair_count": recomputed["pair_count"],
        "edge_count": recomputed["edge_count"],
        "unknown_area": sum(1 for row in all_rows if not row.get("area_sqm")),
    }
    db.flush()
    logger.info(
        "[ingest] %s fetched=%s created=%s updated=%s clusters=%s dedup=%s flags=%s throttled=%s",
        run.run_no, items, created, updated, run.cluster_count, run.dedup_count, run.flag_count, throttled,
    )
    return run


def serialize(run: IngestRun) -> dict:
    from src.constants.enums import INGEST_STATUS_LABELS, TRIGGER_LABELS

    return {
        "id": run.id,
        "run_no": run.run_no,
        "trigger": run.trigger_kind,
        "trigger_label": TRIGGER_LABELS.get(run.trigger_kind, run.trigger_kind),
        "status": run.status,
        "status_label": INGEST_STATUS_LABELS.get(run.status, run.status),
        "sources_total": run.sources_total,
        "pages_fetched": run.pages_fetched,
        "items_fetched": run.items_fetched,
        "throttled_count": run.throttled_count,
        "backoff_ms": run.backoff_ms,
        "created_count": run.created_count,
        "updated_count": run.updated_count,
        "cluster_count": run.cluster_count,
        "duplicate_count": run.duplicate_count,
        "dedup_count": run.dedup_count,
        "flag_count": run.flag_count,
        "duration_ms": run.duration_ms,
        "operator_email": run.operator_email,
        "message": run.message,
        "started_at": iso_utc(run.started_at),
        "finished_at": iso_utc(run.finished_at),
        "summary": run.summary or {},
    }


def list_runs(db: Session, limit: int = 20) -> dict:
    rows = db.scalars(select(IngestRun).order_by(IngestRun.id.desc()).limit(limit)).all()
    return {"items": [serialize(row) for row in rows]}


def latest_run(db: Session) -> IngestRun | None:
    return db.scalar(select(IngestRun).order_by(IngestRun.id.desc()).limit(1))


def pending_flags(db: Session) -> int:
    return len(
        db.scalars(
            select(PriceFlag.id).where(PriceFlag.review_status == ReviewStatus.PENDING.value)
        ).all()
    )
