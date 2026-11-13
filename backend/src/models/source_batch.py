from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base
from src.utils.timeutil import utcnow


class SourceBatch(Base):
    """来源级落批记录：每个采集源在每次运行里收到 / 隔离 / 替换多少条及原因。

    口径：
      · status=isolated  取数不完整（异常 / 分页缺页 / 空快照），整源隔离，
        该来源挂牌一条都不改写；旧挂牌全部置 quarantined=True
      · status=replaced  本次快照完整，按 (source_id, source_listing_no) 原子替换：
        自然键不变的行原地更新（id 不变 → 复核态/工单不漂移），
        快照里消失的挂牌才删除，新挂牌插入
      · status=unchanged 快照内容哈希与上一生效批一致，重复运行只生效一次：
        不写挂牌、不重算
    """

    __tablename__ = "source_batches"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("ingest_runs.id"), index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    source_code: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(12), index=True)
    pages_expected: Mapped[int] = mapped_column(Integer, default=0)
    pages_fetched: Mapped[int] = mapped_column(Integer, default=0)
    received_count: Mapped[int] = mapped_column(Integer, default=0)
    isolated_count: Mapped[int] = mapped_column(Integer, default=0)
    replaced_count: Mapped[int] = mapped_column(Integer, default=0)
    created_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, default=0)
    deleted_count: Mapped[int] = mapped_column(Integer, default=0)
    throttled_count: Mapped[int] = mapped_column(Integer, default=0)
    backoff_ms: Mapped[int] = mapped_column(Integer, default=0)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
