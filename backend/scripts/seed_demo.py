"""幂等 seed：3 账号 / 5 采集源 / 240 挂牌（32 组重复共 78 条）/ 12 个价格工单。

自然键 upsert：
  users.email
  sources.code
  listings(source_id, source_listing_no)
  listing_clusters.primary_listing_id     （由 cluster_service.recompute 维护）
  price_flags.listing_id                  （同上，保留人工复核态）
  ingest_runs.seed_key
  audit_logs.seed_key

重复执行不新增、不覆盖用户改过的数据；SEED_SUMMARY 逐字一致。
"""
from __future__ import annotations

import json
from datetime import date, datetime

from sqlalchemy import func, select

from src.config.database import session_scope
from src.models.audit import AuditLog
from src.models.block_stat import BlockStat
from src.models.cluster import ListingCluster
from src.models.ingest_run import IngestRun
from src.models.listing import Listing
from src.models.price_flag import PriceFlag
from src.models.source import Source
from src.models.user import User
from src.services import cluster_service, fetch_service
from src.utils.security import hash_password
from src.utils.timeutil import utcnow

from scripts.demo_config import DEMO_PASSWORD, DEMO_USERS, HISTORY_RUNS, SEED_AUDIT


def ensure_users(db) -> int:
    for email, display_name, role in DEMO_USERS:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            db.add(
                User(
                    email=email,
                    password_hash=hash_password(DEMO_PASSWORD),
                    display_name=display_name,
                    role=role,
                )
            )
    db.flush()
    return db.scalar(select(func.count()).select_from(User)) or 0


def ensure_sources(db) -> dict[str, Source]:
    specs = fetch_service.load_sources()
    result: dict[str, Source] = {}
    for index, spec in enumerate(specs):
        source = db.scalar(select(Source).where(Source.code == spec["code"]))
        if source is None:
            source = Source(
                code=spec["code"],
                name=spec["name"],
                platform=spec["platform"],
                base_url=spec["base_url"],
                frequency=spec["frequency"],
                rate_limit_per_min=spec["rate_limit_per_min"],
                page_size=spec["page_size"],
                note=spec["note"],
                sort_order=index,
                enabled=True,
            )
            db.add(source)
            db.flush()
        result[source.code] = source
    return result


def ensure_listings(db) -> tuple[int, int]:
    sources = {source.code: source for source in db.scalars(select(Source)).all()}
    platforms = fetch_service.load_platforms()
    created = updated = 0
    for code, source in sources.items():
        if code not in platforms["platforms"]:
            continue
        outcome = fetch_service.crawl_source(
            {"code": code, "name": source.name}, platforms, simulate_throttle=False
        )
        for row in outcome["rows"]:
            listing = db.scalar(
                select(Listing).where(
                    Listing.source_id == source.id,
                    Listing.source_listing_no == row["source_listing_no"],
                )
            )
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
            listing.raw = json.dumps(row.get("raw") or {}, ensure_ascii=False)
        db.flush()
    return created, updated


def ensure_history_runs(db) -> None:
    for seed_key, stamp, sources, pages, items, throttled, backoff, status, message in HISTORY_RUNS:
        if db.scalar(select(IngestRun).where(IngestRun.seed_key == seed_key)):
            continue
        started = datetime.fromisoformat(stamp)
        db.add(
            IngestRun(
                run_no=f"HIST-{stamp[:10]}",
                trigger_kind="schedule",
                status=status,
                sources_total=sources,
                pages_fetched=pages,
                items_fetched=items,
                throttled_count=throttled,
                backoff_ms=backoff,
                created_count=items,
                updated_count=0,
                cluster_count=194,
                duplicate_count=32,
                dedup_count=194,
                flag_count=12,
                duration_ms=4200,
                operator_email="scheduler@rentlens.io",
                message=message,
                summary={"seeded": True},
                started_at=started,
                finished_at=started.replace(minute=started.minute + 1),
                seed_key=seed_key,
            )
        )
    db.flush()


def ensure_seed_audit(db) -> None:
    for seed_key, email, role, action, entity, entity_id, detail in SEED_AUDIT:
        if db.scalar(select(AuditLog).where(AuditLog.seed_key == seed_key)):
            continue
        db.add(
            AuditLog(
                actor_email=email,
                actor_role=role,
                action=action,
                entity=entity,
                entity_id=entity_id,
                detail=detail,
                layer="seed",
                ip="127.0.0.1",
                seed_key=seed_key,
            )
        )
    db.flush()


def seed_all() -> str:
    with session_scope() as db:
        user_count = ensure_users(db)
        ensure_sources(db)
        ensure_listings(db)
        cluster_service.recompute(db)
        ensure_history_runs(db)
        ensure_seed_audit(db)

        source_count = db.scalar(select(func.count()).select_from(Source)) or 0
        listing_count = db.scalar(select(func.count()).select_from(Listing)) or 0
        cluster_count = (
            db.scalar(
                select(func.count()).select_from(ListingCluster).where(ListingCluster.member_count > 1)
            )
            or 0
        )
        flag_count = db.scalar(select(func.count()).select_from(PriceFlag)) or 0
        block_count = db.scalar(select(func.count()).select_from(BlockStat)) or 0

    summary = (
        f"SEED_SUMMARY brand=rentlens sources={source_count} listings={listing_count} "
        f"clusters={cluster_count} flags={flag_count} users={user_count}"
    )
    print(summary, flush=True)
    print(f"SEED_DETAIL blocks={block_count}", flush=True)
    return summary


if __name__ == "__main__":
    seed_all()
