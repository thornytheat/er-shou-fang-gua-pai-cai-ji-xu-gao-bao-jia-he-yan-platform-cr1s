"""去重簇 + 均价快照 + 价格工单的重算（把纯算法落到库里）。

一次 recompute 做三件事：
  1. 用 fingerprint_service 在「全部挂牌」上切簇，写 listing_clusters 与 listing.cluster_id
  2. 按 小区×户型 写 block_stats（去重前 naive_mean / 去重后 dedup_mean / 中位 / MAD）
  3. 在去重后的主房源上跑稳健 z，upsert price_flags（保留人工复核态）
"""
from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from src.constants.enums import FlagType, ReviewStatus
from src.models.block_stat import BlockStat
from src.models.cluster import ListingCluster
from src.models.listing import Listing
from src.models.price_flag import PriceFlag
from src.services.fingerprint_service import build_clusters
from src.services.price_service import block_stats, classify
from src.utils.similarity import similarity_breakdown
from src.utils.timeutil import iso_date, utcnow


def _listing_dicts(db: Session) -> list[dict]:
    rows = db.scalars(select(Listing)).all()
    return [
        {
            "id": row.id,
            "source_id": row.source_id,
            "community": row.community,
            "layout": row.layout,
            "area_sqm": int(row.area_sqm) if row.area_sqm else None,
            "floor": row.floor,
            "total_floors": row.total_floors,
            "title": row.title,
            "unit_price": row.unit_price,
            "list_date": iso_date(row.list_date),
            "completeness": row.completeness,
        }
        for row in rows
    ]


def recompute(db: Session) -> dict:
    rows = _listing_dicts(db)
    result = build_clusters(rows)
    by_id = {row["id"]: row for row in rows}

    # 1) 清空旧归属，重建簇（自然键 = 主房源 id，重跑稳定）
    db.execute(Listing.__table__.update().values(cluster_id=None, is_primary=False))
    existing = {cluster.primary_listing_id: cluster for cluster in db.scalars(select(ListingCluster)).all()}
    primary_ids: set[int] = set()
    member_total = 0

    for cluster in result["clusters"]:
        primary_ids.add(cluster["primary_id"])
        member_total += cluster["member_count"]
        row = existing.get(cluster["primary_id"])
        if row is None:
            row = ListingCluster(
                community=cluster["community"],
                layout=cluster["layout"],
                block_key=f"{cluster['community']}::{cluster['layout']}",
                primary_listing_id=cluster["primary_id"],
            )
            db.add(row)
            db.flush()
        row.member_count = cluster["member_count"]
        row.platform_count = cluster["platform_count"]
        row.avg_unit_price = cluster["avg_unit_price"]
        row.min_similarity = cluster["min_similarity"]
        row.max_similarity = cluster["max_similarity"]
        member_prices = [by_id[mid]["unit_price"] for mid in cluster["member_ids"] if by_id[mid]["unit_price"]]
        row.spread_pct = (
            round((max(member_prices) - min(member_prices)) / (sum(member_prices) / len(member_prices)) * 100, 2)
            if len(member_prices) > 1
            else None
        )
        for member_id in cluster["member_ids"]:
            db.execute(
                Listing.__table__.update()
                .where(Listing.id == member_id)
                .values(cluster_id=row.id, is_primary=member_id == cluster["primary_id"])
            )

    stale = [primary for primary in existing if primary not in primary_ids]
    if stale:
        db.execute(delete(ListingCluster).where(ListingCluster.primary_listing_id.in_(stale)))
    db.flush()

    # 2) 均价快照（两个口径）
    clusters = db.scalars(select(ListingCluster)).all()
    listings = db.scalars(select(Listing)).all()
    listing_by_id = {row.id: row for row in listings}
    block_stats_map: dict[str, dict] = {}
    naive: dict[str, list[float]] = {}
    dedup: dict[str, list[float]] = {}
    unknown: dict[str, int] = {}
    for row in listings:
        key = f"{row.community}::{row.layout}"
        if row.area_sqm and row.unit_price:
            naive.setdefault(key, []).append(float(row.unit_price))
        else:
            unknown[key] = unknown.get(key, 0) + 1
    for cluster in clusters:
        primary = listing_by_id.get(cluster.primary_listing_id)
        if primary is None:
            continue
        key = f"{cluster.community}::{cluster.layout}"
        if primary.area_sqm and primary.unit_price:
            dedup.setdefault(key, []).append(float(primary.unit_price))

    existing_stats = {stat.block_key: stat for stat in db.scalars(select(BlockStat)).all()}
    for key in sorted(set(naive) | set(dedup)):
        community, layout = key.split("::", 1)
        stats = block_stats(dedup.get(key, []))
        naive_values = naive.get(key, [])
        stat_row = existing_stats.get(key)
        if stat_row is None:
            stat_row = BlockStat(block_key=key, community=community, layout=layout)
            db.add(stat_row)
        stat_row.all_count = len(naive_values)
        stat_row.primary_count = stats["sample_size"]
        stat_row.unknown_count = unknown.get(key, 0)
        stat_row.naive_mean = round(sum(naive_values) / len(naive_values), 2) if naive_values else None
        stat_row.dedup_mean = stats["mean_price"]
        stat_row.median_price = stats["median_price"]
        stat_row.mad = stats["mad"]
        stat_row.min_price = stats["min_price"]
        stat_row.max_price = stats["max_price"]
        stat_row.updated_at = utcnow()
        block_stats_map[key] = stats
    db.flush()

    # 3) 价格工单（只在去重后的主房源上判定，保留人工复核态）
    existing_flags = {flag.listing_id: flag for flag in db.scalars(select(PriceFlag)).all()}
    flagged_ids: set[int] = set()
    counts = {"high": 0, "low": 0, "uncertain": 0}
    for cluster in clusters:
        key = f"{cluster.community}::{cluster.layout}"
        stats = block_stats_map.get(key)
        if not stats or not stats["sample_size"]:
            continue
        primary = listing_by_id.get(cluster.primary_listing_id)
        if primary is None:
            continue
        verdict = classify(
            primary.unit_price,
            median_price=stats["median_price"],
            spread=stats["mad"],
            sample_size=stats["sample_size"],
            completeness=primary.completeness,
        )
        if not verdict["flag_type"]:
            continue
        flagged_ids.add(primary.id)
        counts[verdict["flag_type"]] = counts.get(verdict["flag_type"], 0) + 1
        flag = existing_flags.get(primary.id)
        if flag is None:
            flag = PriceFlag(listing_id=primary.id, review_status=ReviewStatus.PENDING.value)
            db.add(flag)
        flag.cluster_id = cluster.id
        flag.flag_type = verdict["flag_type"]
        flag.community = primary.community
        flag.layout = primary.layout
        flag.unit_price = int(primary.unit_price or 0)
        flag.median_price = float(stats["median_price"] or 0)
        flag.deviation_pct = float(verdict["deviation_pct"] or 0)
        flag.z_score = verdict["z_score"]
        flag.confidence = float(verdict["confidence"] or 0)
        flag.sample_size = int(stats["sample_size"])
        if flag.review_status == ReviewStatus.PENDING.value:
            flag.detected_at = utcnow()
    db.flush()

    stale_flags = [
        flag for flag in db.scalars(select(PriceFlag)).all()
        if flag.listing_id not in flagged_ids and flag.review_status == ReviewStatus.PENDING.value
    ]
    for flag in stale_flags:
        db.delete(flag)
    db.flush()
    # 簇归属是用批量 UPDATE 写的，让会话里的对象失效，避免同一请求读到旧 cluster_id
    db.expire_all()

    return {
        "cluster_count": len(result["clusters"]),
        "duplicate_count": result.get("duplicate_clusters", 0),
        "dedup_count": result["dedup_count"],
        "member_total": member_total,
        "edge_count": result["edge_count"],
        "pair_count": result["pair_count"],
        "flag_counts": counts,
        "flag_total": sum(counts.values()),
        "blocks": len(block_stats_map),
    }


def similarity_for(db: Session, cluster_id: int, member_id: int) -> float | None:
    """簇内成员与主房源的加权相似度（详情页并排对比用）。"""
    cluster = db.get(ListingCluster, cluster_id)
    if cluster is None:
        return None
    primary = db.get(Listing, cluster.primary_listing_id)
    member = db.get(Listing, member_id)
    if primary is None or member is None or primary.id == member.id:
        return None
    breakdown = similarity_breakdown(
        {
            "area_sqm": int(primary.area_sqm) if primary.area_sqm else None,
            "floor": primary.floor,
            "title": primary.title,
            "unit_price": primary.unit_price,
        },
        {
            "area_sqm": int(member.area_sqm) if member.area_sqm else None,
            "floor": member.floor,
            "title": member.title,
            "unit_price": member.unit_price,
        },
    )
    return breakdown["score"]


def flag_type_counts(db: Session) -> dict:
    rows = db.execute(
        select(PriceFlag.flag_type, func.count()).group_by(PriceFlag.flag_type)
    ).all()
    counts = {FlagType.HIGH.value: 0, FlagType.LOW.value: 0, FlagType.UNCERTAIN.value: 0}
    for flag_type, total in rows:
        counts[flag_type] = int(total)
    return counts
