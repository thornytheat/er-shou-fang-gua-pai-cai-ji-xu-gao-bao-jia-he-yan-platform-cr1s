"""采集编排：源 → 页面 → 解析 → 按源完整落批 → 去重 → 均价刷新 → 价格核验。

落批口径（按来源整批处理，不再跨源混写）：
  1. 取数不完整（异常 / 分页缺页 / 空快照）→ 整源隔离：该来源挂牌一条不改写，
     旧挂牌全部置 quarantined=True，不进去重、均价、工单与导出。
  2. 取数完整 → 计算快照内容哈希；与上一生效批一致则 unchanged（重复运行只生效一次，
     不写挂牌、不重算）；不一致则按本次快照原子替换该来源：
     自然键 (source_id, source_listing_no) 不变的行原地更新（行 id 不变，
     人工复核与改价结果继续挂在原房上，不漂移），消失的挂牌删除、新挂牌插入。
  3. 只有发生替换或隔离态变化时才重算簇 / 均价 / 工单；每次源级处理都写 source_batches，
     记录收到、隔离、替换条数与原因。
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.constants.enums import (
    IngestStatus,
    QuarantineReason,
    ReviewStatus,
    SourceBatchStatus,
    TriggerKind,
)
from src.constants.limits import MAX_ITEMS_PER_RUN
from src.models.block_stat import BlockStat
from src.models.ingest_run import IngestRun
from src.models.listing import Listing
from src.models.price_flag import PriceFlag
from src.models.source import Source
from src.models.source_batch import SourceBatch
from src.services import cluster_service, fetch_service
from src.services.fetch_service import FetchIncomplete
from src.utils.errors import AppError
from src.utils.logger import get_logger
from src.utils.timeutil import iso_utc, utcnow

logger = get_logger("ingest")

# 参与内容哈希的归一化字段（raw_json 是平台原文，不参与；只认解析后的口径字段）
_HASH_FIELDS = (
    "source_listing_no", "community", "layout", "area_sqm", "floor", "total_floors",
    "floor_band", "unit_price", "total_price_wan", "list_date", "title",
    "agent_name", "agent_contact", "completeness",
)


def _next_run_no(db: Session) -> str:
    stamp = utcnow().strftime("%Y%m%d%H%M%S")
    seq = len(db.scalars(select(IngestRun.id)).all()) + 1
    return f"RUN-{stamp}-{seq:02d}"


def assert_not_running(db: Session) -> None:
    running = db.scalar(select(IngestRun).where(IngestRun.status == IngestStatus.RUNNING.value))
    if running is not None:
        raise AppError("INGEST_RUNNING", 409, detail={"run_no": running.run_no})


def _content_hash(rows: list[dict]) -> str:
    """快照内容哈希：同输入逐字一致，同一批重复运行哈希不变 → 只生效一次。"""
    canonical = [
        {field: row.get(field) for field in _HASH_FIELDS}
        for row in sorted(rows, key=lambda row: row["source_listing_no"])
    ]
    payload = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _latest_effective_hash(db: Session, source_id: int) -> str | None:
    """上一生效批（replaced）的内容哈希；unchanged/isolated 不作为比对基线。"""
    batch = db.scalar(
        select(SourceBatch)
        .where(
            SourceBatch.source_id == source_id,
            SourceBatch.status == SourceBatchStatus.REPLACED.value,
        )
        .order_by(SourceBatch.id.desc())
        .limit(1)
    )
    return batch.content_hash if batch else None


def _apply_row(listing: Listing, row: dict) -> None:
    list_date = date.fromisoformat(row["list_date"]) if row.get("list_date") else None
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
    # 完整快照生效即解除该源挂牌的隔离态
    listing.quarantined = False


def replace_source_snapshot(db: Session, source: Source, rows: list[dict]) -> dict:
    """按本次完整快照原子替换单个来源的挂牌（自然键稳定，行 id 尽量不变）。

    同 (source_id, source_listing_no) 的行原地更新 → 价格工单（listing_id 外键）
    与人工复核结果继续对应原房；仅快照里消失的挂牌才删除，并清掉它的工单。
    """
    existing = {
        row.source_listing_no: row
        for row in db.scalars(select(Listing).where(Listing.source_id == source.id)).all()
    }
    incoming_keys = {row["source_listing_no"] for row in rows[:MAX_ITEMS_PER_RUN]}
    created = updated = 0

    for row in rows[:MAX_ITEMS_PER_RUN]:
        key = row["source_listing_no"]
        listing = existing.get(key)
        if listing is None:
            listing = Listing(
                source_id=source.id,
                source_listing_no=key,
                community=row["community"],
                layout=row["layout"],
            )
            db.add(listing)
            created += 1
        else:
            updated += 1
        _apply_row(listing, row)

    removed_flags: list[dict] = []
    stale_keys = [key for key in existing if key not in incoming_keys]
    for key in stale_keys:
        stale = existing[key]
        flag = db.scalar(select(PriceFlag).where(PriceFlag.listing_id == stale.id))
        if flag is not None:
            removed_flags.append(
                {
                    "flag_id": flag.id,
                    "source_listing_no": key,
                    "review_status": flag.review_status,
                    "flag_type": flag.flag_type,
                }
            )
            db.delete(flag)
        db.delete(stale)
    db.flush()
    return {
        "created": created,
        "updated": updated,
        "deleted": len(stale_keys),
        "replaced": len(rows[:MAX_ITEMS_PER_RUN]),
        "removed_flags": removed_flags,
    }


def quarantine_source(db: Session, source: Source) -> int:
    """整源隔离：保留旧挂牌但全部置 quarantined=True，返回隔离条数。"""
    rows = db.scalars(select(Listing).where(Listing.source_id == source.id)).all()
    changed = 0
    for row in rows:
        if not row.quarantined:
            row.quarantined = True
            changed += 1
        # 隔离态挂牌不再属于任何有效簇
        row.cluster_id = None
        row.is_primary = False
    db.flush()
    return len(rows), changed


def _quarantine_state_changed(db: Session, source: Source) -> bool:
    """该来源当前是否存在隔离态挂牌（用于判断重算必要性）。"""
    return db.scalar(
        select(Listing.id).where(
            Listing.source_id == source.id, Listing.quarantined.is_(True)
        ).limit(1)
    ) is not None


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
    pages = items = throttled = backoff = 0
    created_total = updated_total = deleted_total = replaced_total = isolated_total = 0
    throttle_log: list[dict] = []
    batch_rows: list[dict] = []
    isolated_sources = 0
    needs_recompute = False
    unknown_area = 0

    for source in enabled:
        batch = SourceBatch(run_id=run.id, source_id=source.id, source_code=source.code)
        try:
            outcome = fetch_service.crawl_source(
                {"code": source.code, "name": source.name}, platforms
            )
        except FetchIncomplete as exc:
            logger.warning("[ingest] %s isolated: %s", source.code, exc)
            isolated_count, changed = quarantine_source(db, source)
            batch.status = SourceBatchStatus.ISOLATED.value
            batch.pages_expected = exc.pages_expected
            batch.pages_fetched = exc.pages_fetched
            batch.received_count = getattr(exc, "items_fetched", 0)
            batch.isolated_count = isolated_count
            batch.reason = exc.reason
            batch.detail = {"message": exc.detail}
            source.last_run_status = IngestStatus.FAILED.value
            source.last_run_items = 0
            isolated_sources += 1
            needs_recompute = needs_recompute or changed > 0
            isolated_total += isolated_count
        except Exception as exc:  # noqa: BLE001 - 任何意外都按整源隔离，不能脏写
            logger.warning("[ingest] %s isolated (unexpected): %s", source.code, exc)
            isolated_count, changed = quarantine_source(db, source)
            batch.status = SourceBatchStatus.ISOLATED.value
            batch.reason = QuarantineReason.FETCH_CRASH.value
            batch.received_count = 0
            batch.isolated_count = isolated_count
            batch.detail = {"message": str(exc)}
            source.last_run_status = IngestStatus.FAILED.value
            source.last_run_items = 0
            isolated_sources += 1
            needs_recompute = needs_recompute or changed > 0
            isolated_total += isolated_count
        else:
            rows = outcome["rows"]
            pages += outcome["pages_fetched"]
            items += outcome["items_fetched"]
            throttled += outcome["throttled"]
            backoff += outcome["backoff_ms"]
            throttle_log.extend(
                {"source": source.code, **entry} for entry in outcome["throttle_log"]
            )
            unknown_area += sum(1 for row in rows if not row.get("area_sqm"))
            batch.pages_expected = outcome["pages_expected"]
            batch.pages_fetched = outcome["pages_fetched"]
            batch.received_count = outcome["items_fetched"]
            batch.throttled_count = outcome["throttled"]
            batch.backoff_ms = outcome["backoff_ms"]
            batch.content_hash = _content_hash(rows)

            if (
                batch.content_hash == _latest_effective_hash(db, source.id)
                and not _quarantine_state_changed(db, source)
            ):
                # 同一批重复运行：快照逐字一致且该源没有隔离态挂牌，只生效一次——
                # 不写挂牌、不重算。若该源正处于隔离态，即使哈希相同也必须重新落批解除隔离。
                batch.status = SourceBatchStatus.UNCHANGED.value
                source.last_run_status = IngestStatus.SUCCESS.value
                source.last_run_items = outcome["items_fetched"]
            else:
                write_summary = replace_source_snapshot(db, source, rows)
                batch.status = SourceBatchStatus.REPLACED.value
                batch.replaced_count = write_summary["replaced"]
                batch.created_count = write_summary["created"]
                batch.updated_count = write_summary["updated"]
                batch.deleted_count = write_summary["deleted"]
                batch.detail = {"removed_flags": write_summary["removed_flags"]}
                created_total += write_summary["created"]
                updated_total += write_summary["updated"]
                deleted_total += write_summary["deleted"]
                replaced_total += write_summary["replaced"]
                source.last_run_status = IngestStatus.SUCCESS.value
                source.last_run_items = outcome["items_fetched"]
                needs_recompute = True
        finally:
            source.last_run_at = utcnow()
            db.add(batch)
            db.flush()
            batch_rows.append(serialize_batch(batch))

    if needs_recompute:
        recomputed = cluster_service.recompute(db)
    else:
        # 全部来源 unchanged 且无隔离态变化：读当前口径回填，不触发任何重算
        recomputed = cluster_service.current_counts(db)

    run.pages_fetched = pages
    run.items_fetched = items
    run.throttled_count = throttled
    run.backoff_ms = backoff
    run.created_count = created_total
    run.updated_count = updated_total
    run.cluster_count = recomputed["cluster_count"]
    run.duplicate_count = recomputed["duplicate_count"]
    run.dedup_count = recomputed["dedup_count"]
    run.flag_count = recomputed["flag_total"]
    run.duration_ms = int((time.time() - started) * 1000)
    run.finished_at = utcnow()
    if isolated_sources == 0:
        run.status = IngestStatus.SUCCESS.value
    elif isolated_sources == len(enabled):
        run.status = IngestStatus.FAILED.value
    else:
        run.status = IngestStatus.PARTIAL.value
    run.message = _run_message(batch_rows)
    run.summary = {
        "throttle_log": throttle_log,
        "flag_counts": recomputed["flag_counts"],
        "blocks": _price_refresh_summary(db),
        "pair_count": recomputed.get("pair_count", 0),
        "edge_count": recomputed.get("edge_count", 0),
        "unknown_area": unknown_area,
        "recomputed": needs_recompute,
        "replaced_total": replaced_total,
        "isolated_total": isolated_total,
        "deleted_total": deleted_total,
        "source_batches": batch_rows,
    }
    db.flush()
    logger.info(
        "[ingest] %s status=%s fetched=%s replaced=%s isolated=%s created=%s updated=%s "
        "clusters=%s dedup=%s flags=%s throttled=%s recomputed=%s",
        run.run_no, run.status, items, replaced_total, isolated_total,
        created_total, updated_total, run.cluster_count, run.dedup_count,
        run.flag_count, throttled, needs_recompute,
    )
    return run


def _run_message(batch_rows: list[dict]) -> str:
    parts = []
    for batch in batch_rows:
        if batch["status"] == SourceBatchStatus.ISOLATED.value:
            parts.append(f"{batch['source_code']} 已整源隔离（{batch['reason']}，旧挂牌不参与均价/工单/导出）")
        elif batch["status"] == SourceBatchStatus.REPLACED.value:
            parts.append(
                f"{batch['source_code']} 原子替换 {batch['replaced_count']} 条"
                f"（新增 {batch['created_count']} / 更新 {batch['updated_count']} / 删除 {batch['deleted_count']}）"
            )
        else:
            parts.append(f"{batch['source_code']} 快照与上批一致，重复运行跳过")
    return "；".join(parts)


def serialize_batch(batch: SourceBatch) -> dict:
    return {
        "id": batch.id,
        "run_id": batch.run_id,
        "source_id": batch.source_id,
        "source_code": batch.source_code,
        "status": batch.status,
        "pages_expected": batch.pages_expected,
        "pages_fetched": batch.pages_fetched,
        "received_count": batch.received_count,
        "isolated_count": batch.isolated_count,
        "replaced_count": batch.replaced_count,
        "created_count": batch.created_count,
        "updated_count": batch.updated_count,
        "deleted_count": batch.deleted_count,
        "throttled_count": batch.throttled_count,
        "backoff_ms": batch.backoff_ms,
        "content_hash": batch.content_hash,
        "reason": batch.reason,
        "detail": batch.detail or {},
        "created_at": iso_utc(batch.created_at),
    }


def list_batches_by_run(db: Session, run_id: int) -> list[dict]:
    rows = db.scalars(
        select(SourceBatch).where(SourceBatch.run_id == run_id).order_by(SourceBatch.id)
    ).all()
    return [serialize_batch(row) for row in rows]


def latest_batches(db: Session) -> list[dict]:
    """每个来源最近一次落批结果（采集源页「本源最近批次」用）。"""
    rows = db.scalars(select(SourceBatch).order_by(SourceBatch.source_id, SourceBatch.id)).all()
    latest: dict[int, SourceBatch] = {}
    for row in rows:
        latest[row.source_id] = row
    return [serialize_batch(row) for row in latest.values()]


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
