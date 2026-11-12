from __future__ import annotations

from pydantic import BaseModel


class ClusterRow(BaseModel):
    id: int
    community: str
    layout: str
    block_key: str
    primary_listing_id: int
    member_count: int
    platform_count: int
    avg_unit_price: float | None = None
    min_similarity: float | None = None
    max_similarity: float | None = None
    spread_pct: float | None = None
    primary_title: str | None = None


class ClusterPage(BaseModel):
    items: list[ClusterRow]
    total: int
    duplicate_total: int
    dedup_total: int
