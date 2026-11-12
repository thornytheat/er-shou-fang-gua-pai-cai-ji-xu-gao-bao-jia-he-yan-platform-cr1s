from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base
from src.utils.timeutil import utcnow


class ListingCluster(Base):
    """实体 3：去重簇（主房源 + 成员数 + 跨平台数）。"""

    __tablename__ = "listing_clusters"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    community: Mapped[str] = mapped_column(String(40), index=True)
    layout: Mapped[str] = mapped_column(String(12), index=True)
    block_key: Mapped[str] = mapped_column(String(60), index=True)
    primary_listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), unique=True)
    member_count: Mapped[int] = mapped_column(Integer, default=1)
    platform_count: Mapped[int] = mapped_column(Integer, default=1)
    avg_unit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    min_similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    spread_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
