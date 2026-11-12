"""行情 CSV 导出：按「去重后的主房源」出行情明细，附价格标记与偏离度。"""
from __future__ import annotations

import csv
import io
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.constants.enums import FLAG_TYPE_LABELS, REVIEW_LABELS
from src.models.block_stat import BlockStat
from src.models.cluster import ListingCluster
from src.models.listing import Listing
from src.models.price_flag import PriceFlag
from src.models.source import Source
from src.utils.errors import AppError
from src.utils.timeutil import iso_date

HEADERS = [
    "小区",
    "户型",
    "面积㎡",
    "楼层",
    "挂牌日",
    "来源平台",
    "挂牌编号",
    "单价(元/㎡)",
    "总价(万)",
    "簇成员数",
    "跨平台数",
    "价格标记",
    "偏离中位%",
    "稳健z",
    "置信度",
    "复核状态",
    "小区户型中位价",
    "去重后均价",
    "去重前均价",
]


def rows_for_export(
    db: Session,
    *,
    community: str | None = None,
    since: str | None = None,
    flag_only: bool = False,
) -> list[list]:
    query = select(Listing).where(Listing.is_primary.is_(True))
    if community:
        query = query.where(Listing.community == community)
    if since:
        try:
            query = query.where(Listing.list_date >= date.fromisoformat(since))
        except ValueError as exc:
            raise AppError("VALIDATION", 422, detail=f"since={since}") from exc
    listings = db.scalars(query.order_by(Listing.community, Listing.layout, Listing.unit_price)).all()
    sources = {source.id: source for source in db.scalars(select(Source)).all()}
    clusters = {cluster.id: cluster for cluster in db.scalars(select(ListingCluster)).all()}
    flags = {flag.listing_id: flag for flag in db.scalars(select(PriceFlag)).all()}
    stats = {stat.block_key: stat for stat in db.scalars(select(BlockStat)).all()}

    rows: list[list] = []
    for listing in listings:
        flag = flags.get(listing.id)
        if flag_only and flag is None:
            continue
        cluster = clusters.get(listing.cluster_id) if listing.cluster_id else None
        stat = stats.get(f"{listing.community}::{listing.layout}")
        rows.append(
            [
                listing.community,
                listing.layout,
                f"{listing.area_sqm:.0f}" if listing.area_sqm else "",
                f"{listing.floor}/{listing.total_floors}" if listing.floor and listing.total_floors else (listing.floor_band or ""),
                iso_date(listing.list_date) or "",
                sources[listing.source_id].name if listing.source_id in sources else "",
                listing.source_listing_no,
                listing.unit_price if listing.unit_price else "",
                f"{listing.total_price_wan:.2f}" if listing.total_price_wan else "",
                cluster.member_count if cluster else 1,
                cluster.platform_count if cluster else 1,
                FLAG_TYPE_LABELS.get(flag.flag_type, "") if flag else "",
                f"{flag.deviation_pct:.2f}" if flag else "",
                f"{flag.z_score:.2f}" if flag and flag.z_score is not None else "",
                f"{flag.confidence:.2f}" if flag else "",
                REVIEW_LABELS.get(flag.review_status, "") if flag else "",
                f"{stat.median_price:.0f}" if stat and stat.median_price else "",
                f"{stat.dedup_mean:.0f}" if stat and stat.dedup_mean else "",
                f"{stat.naive_mean:.0f}" if stat and stat.naive_mean else "",
            ]
        )
    return rows


def build_csv(db: Session, **filters) -> tuple[str, str, int]:
    rows = rows_for_export(db, **filters)
    if not rows:
        raise AppError("EXPORT_EMPTY", 404)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(HEADERS)
    writer.writerows(rows)
    stamp = date.today().strftime("%Y%m%d")
    filename = f"rentlens-market-{stamp}.csv"
    return buffer.getvalue(), filename, len(rows)
