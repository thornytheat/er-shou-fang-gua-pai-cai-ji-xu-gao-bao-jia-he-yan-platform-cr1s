from __future__ import annotations

from pydantic import BaseModel, Field


class ListingRow(BaseModel):
    id: int
    source_id: int
    source_name: str
    source_platform: str
    source_listing_no: str
    community: str
    layout: str
    area_sqm: float | None = None
    floor: int | None = None
    total_floors: int | None = None
    floor_band: str | None = None
    unit_price: int | None = None
    total_price_wan: float | None = None
    list_date: str | None = None
    title: str
    agent_name: str | None = None
    agent_contact: str | None = None
    completeness: float = 1.0
    cluster_id: int | None = None
    cluster_size: int = 1
    platform_count: int = 1
    is_primary: bool = False
    quarantined: bool = False
    flag_type: str | None = None
    flag_label: str | None = None
    deviation_pct: float | None = None
    review_status: str | None = None


class ListingPage(BaseModel):
    items: list[ListingRow]
    total: int
    page: int
    page_size: int
    sums: dict = {}


class ListingMember(BaseModel):
    id: int
    source_name: str
    source_platform: str
    source_listing_no: str
    unit_price: int | None = None
    total_price_wan: float | None = None
    list_date: str | None = None
    title: str
    floor: int | None = None
    floor_band: str | None = None
    similarity: float | None = None
    is_primary: bool = False


class ListingDetail(BaseModel):
    listing: ListingRow
    members: list[ListingMember] = []
    block: dict = {}
    flag: dict | None = None
    price_series: list[dict] = []


class PriceFixIn(BaseModel):
    unit_price: int = Field(ge=1000, le=300000)
    note: str = Field(min_length=2, max_length=200)
