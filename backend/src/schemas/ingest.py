from __future__ import annotations

from pydantic import BaseModel, Field


class IngestRunIn(BaseModel):
    source_ids: list[int] | None = Field(default=None, description="留空表示采集全部启用的源")


class IngestRunOut(BaseModel):
    id: int
    run_no: str
    trigger: str
    trigger_label: str
    status: str
    status_label: str
    sources_total: int
    pages_fetched: int
    items_fetched: int
    throttled_count: int
    backoff_ms: int
    created_count: int
    updated_count: int
    cluster_count: int
    duplicate_count: int
    dedup_count: int
    flag_count: int
    duration_ms: int
    operator_email: str
    message: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    summary: dict = {}
