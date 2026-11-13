"""ORM 模型聚合导出（Base 用于 create_all）。"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


from src.models.user import User  # noqa: E402
from src.models.audit import AuditLog  # noqa: E402
from src.models.source import Source  # noqa: E402
from src.models.listing import Listing  # noqa: E402
from src.models.cluster import ListingCluster  # noqa: E402
from src.models.price_flag import PriceFlag  # noqa: E402
from src.models.ingest_run import IngestRun  # noqa: E402
from src.models.block_stat import BlockStat  # noqa: E402
from src.models.source_batch import SourceBatch  # noqa: E402

__all__ = [
    "Base",
    "User",
    "AuditLog",
    "Source",
    "Listing",
    "ListingCluster",
    "PriceFlag",
    "IngestRun",
    "BlockStat",
    "SourceBatch",
]
