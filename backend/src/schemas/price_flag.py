from __future__ import annotations

from pydantic import BaseModel, Field


class PriceFlagRow(BaseModel):
    id: int
    listing_id: int
    cluster_id: int | None = None
    flag_type: str
    flag_label: str
    community: str
    layout: str
    unit_price: int
    median_price: float
    deviation_pct: float
    z_score: float | None = None
    confidence: float
    sample_size: int
    review_status: str
    review_label: str
    review_note: str | None = None
    reviewed_by: str | None = None
    reviewed_at: str | None = None
    detected_at: str | None = None
    title: str | None = None
    area_sqm: float | None = None
    list_date: str | None = None
    source_name: str | None = None


class PriceFlagPage(BaseModel):
    items: list[PriceFlagRow]
    total: int
    counts: dict = {}


class ReviewIn(BaseModel):
    review_status: str = Field(pattern="^(pending|confirmed|dismissed)$")
    note: str | None = Field(default=None, max_length=300)
