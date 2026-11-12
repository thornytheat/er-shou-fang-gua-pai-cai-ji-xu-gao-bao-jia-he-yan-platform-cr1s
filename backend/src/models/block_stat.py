from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base
from src.utils.timeutil import utcnow


class BlockStat(Base):
    """支撑表：小区×户型 的均价/中位/MAD 快照（去重前后两个口径）。"""

    __tablename__ = "block_stats"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    block_key: Mapped[str] = mapped_column(String(60), unique=True)
    community: Mapped[str] = mapped_column(String(40), index=True)
    layout: Mapped[str] = mapped_column(String(12), index=True)
    all_count: Mapped[int] = mapped_column(Integer, default=0)
    primary_count: Mapped[int] = mapped_column(Integer, default=0)
    unknown_count: Mapped[int] = mapped_column(Integer, default=0)
    naive_mean: Mapped[float | None] = mapped_column(Float, nullable=True)
    dedup_mean: Mapped[float | None] = mapped_column(Float, nullable=True)
    median_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    mad: Mapped[float | None] = mapped_column(Float, nullable=True)
    min_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
