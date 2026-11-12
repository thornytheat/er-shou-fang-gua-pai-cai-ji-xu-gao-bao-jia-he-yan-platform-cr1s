"""共享枚举（后端唯一定义处）。前端副本见 frontend/src/constants/enums.ts。

README「共享枚举出现位置」一节列出全部出现点，改动需两侧同步。
"""
from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    """三角色：研究组长 / 数据专员 / 中介客户（只读）。"""

    ADMIN = "admin"
    ANALYST = "analyst"
    CLIENT = "client"


class PlatformKind(StrEnum):
    """五个采集平台的形态（决定解析器与标题风格）。"""

    AGGREGATOR = "aggregator"      # 链家式聚合站：字段规整、有精确楼层
    PORTAL = "portal"              # 安居式信息港：楼层是「中楼层(共18层)」
    FORUM = "forum"                # 业主论坛：口语化、日期是中文
    MOMENTS = "moments"            # 中介朋友圈存档：截图式摘要、带电话
    NOTICE = "notice"              # 门店群公告：一行一条、日期只有 MM-DD


PLATFORM_LABELS: dict[str, str] = {
    PlatformKind.AGGREGATOR.value: "链家式聚合站",
    PlatformKind.PORTAL.value: "安居式信息港",
    PlatformKind.FORUM.value: "业主论坛",
    PlatformKind.MOMENTS.value: "中介朋友圈存档",
    PlatformKind.NOTICE.value: "门店群公告",
}


class Layout(StrEnum):
    ONE = "一居"
    TWO = "两居"
    THREE = "三居"


LAYOUT_ORDER: list[str] = [Layout.ONE.value, Layout.TWO.value, Layout.THREE.value]


class FloorBand(StrEnum):
    LOW = "低楼层"
    MID = "中楼层"
    HIGH = "高楼层"


FLOOR_BAND_ORDER: list[str] = [
    FloorBand.LOW.value,
    FloorBand.MID.value,
    FloorBand.HIGH.value,
]


class IngestStatus(StrEnum):
    """一次采集运行的状态。"""

    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class FlagType(StrEnum):
    """价格异常工单类型：虚高 / 虚低 / 待确认（边界样本）。"""

    HIGH = "high"
    LOW = "low"
    UNCERTAIN = "uncertain"


FLAG_TYPE_LABELS: dict[str, str] = {
    FlagType.HIGH.value: "虚高",
    FlagType.LOW.value: "虚低",
    FlagType.UNCERTAIN.value: "待确认",
}

FLAG_TYPE_ORDER: list[str] = [FlagType.HIGH.value, FlagType.LOW.value, FlagType.UNCERTAIN.value]


class ReviewStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"


REVIEW_LABELS: dict[str, str] = {
    ReviewStatus.PENDING.value: "待复核",
    ReviewStatus.CONFIRMED.value: "已确认",
    ReviewStatus.DISMISSED.value: "已驳回",
}


class TriggerKind(StrEnum):
    MANUAL = "manual"
    SCHEDULE = "schedule"
    SEED = "seed"


TRIGGER_LABELS: dict[str, str] = {
    TriggerKind.MANUAL.value: "手动",
    TriggerKind.SCHEDULE.value: "定时",
    TriggerKind.SEED.value: "初始化",
}

INGEST_STATUS_LABELS: dict[str, str] = {
    IngestStatus.RUNNING.value: "运行中",
    IngestStatus.SUCCESS.value: "成功",
    IngestStatus.PARTIAL.value: "部分成功",
    IngestStatus.FAILED.value: "失败",
}
