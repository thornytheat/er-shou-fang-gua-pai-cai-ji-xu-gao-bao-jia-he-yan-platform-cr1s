from __future__ import annotations

from pydantic import BaseModel, Field


class SourceOut(BaseModel):
    id: int
    code: str
    name: str
    platform: str
    platform_label: str
    base_url: str
    frequency: str
    rate_limit_per_min: int
    page_size: int
    enabled: bool
    last_run_at: str | None = None
    last_run_status: str | None = None
    last_run_items: int = 0
    listing_count: int = 0
    note: str | None = None
    latest_batch: dict | None = None


class SourcePatchIn(BaseModel):
    frequency: str | None = Field(default=None, max_length=40)
    rate_limit_per_min: int | None = Field(default=None, ge=1, le=600)
    page_size: int | None = Field(default=None, ge=5, le=50)
    enabled: bool | None = None
    note: str | None = Field(default=None, max_length=400)


class SourceCreateIn(BaseModel):
    code: str = Field(min_length=3, max_length=40)
    name: str = Field(min_length=2, max_length=80)
    platform: str = Field(pattern="^(aggregator|portal|forum|moments|notice)$")
    base_url: str = Field(min_length=6, max_length=255)
    frequency: str = Field(min_length=3, max_length=40)
    rate_limit_per_min: int = Field(default=30, ge=1, le=600)
    page_size: int = Field(default=10, ge=5, le=50)
    note: str | None = Field(default=None, max_length=400)
