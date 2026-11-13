from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base
from src.utils.timeutil import utcnow


class Listing(Base):
    """实体 2：房源挂牌快照（一个平台一条）。"""

    __tablename__ = "listings"
    __table_args__ = (
        UniqueConstraint("source_id", "source_listing_no", name="uq_listing_source_no"),
        Index("ix_listings_block", "community", "layout"),
        Index("ix_listings_list_date", "list_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    source_listing_no: Mapped[str] = mapped_column(String(40))
    community: Mapped[str] = mapped_column(String(40), index=True)
    layout: Mapped[str] = mapped_column(String(12), index=True)
    area_sqm: Mapped[float | None] = mapped_column(Float, nullable=True)
    floor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_floors: Mapped[int | None] = mapped_column(Integer, nullable=True)
    floor_band: Mapped[str | None] = mapped_column(String(12), nullable=True)
    unit_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_price_wan: Mapped[float | None] = mapped_column(Float, nullable=True)
    list_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    title: Mapped[str] = mapped_column(Text)
    agent_name: Mapped[str | None] = mapped_column(String(60), nullable=True)
    agent_contact: Mapped[str | None] = mapped_column(String(40), nullable=True)
    completeness: Mapped[float] = mapped_column(Float, default=1.0)
    cluster_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    # 整源隔离标记：所属来源最近一次取数不完整时，旧挂牌保留但隔离，
    # 不参与去重簇、均价、价格工单与行情导出（由 ingest_service 按批维护）
    quarantined: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
