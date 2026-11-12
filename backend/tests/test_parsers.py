"""解析/归一工具：五平台字段口径 + 金额/面积/日期归一（纯函数）。"""
from __future__ import annotations

import pytest

from src.services.parsers import (
    PARSERS,
    _to_date,
    parse_anjuke,
    parse_forum,
    parse_lianjia,
    parse_moments,
    parse_notice,
)


# ---------------- 五平台真实 fixture 解析 ----------------

@pytest.mark.parametrize(
    ("kind", "code", "layout", "area", "floor", "band", "unit_price", "total_wan", "completeness", "contact"),
    [
        ("aggregator", "LJ-100201", "三居", 140, 3, "低楼层", 44419, 621.87, 1.0, "139 1122 3344"),
        ("portal", "AJ800301", "两居", 98, 15, "高楼层", 73713, 722.39, 1.0, "139 1122 3344"),
        ("forum", "BBS-700401", "三居", 132, 9, "中楼层", 66399, 876.47, 0.875, None),
        ("moments", "MM-910501", "两居", 90, 3, "低楼层", 36306, 326.75, 1.0, "139 1122 3344"),
        ("notice", "GR-620601", "三居", 124, 15, "高楼层", 63193, 783.59, 0.875, None),
    ],
)
def test_parse_real_fixture_items(
    platform_items: dict[str, dict],
    kind: str,
    code: str,
    layout: str,
    area: int,
    floor: int,
    band: str,
    unit_price: int,
    total_wan: float,
    completeness: float,
    contact: str | None,
) -> None:
    """每个平台第 1 条真实记录 → 统一 Listing 结构（单位/楼层/日期口径拉平）。"""
    row = PARSERS[kind](platform_items[kind])
    assert row["source_listing_no"] == code
    assert row["community"] == "云栖湾"
    assert row["layout"] == layout
    assert row["area_sqm"] == area
    assert row["floor"] == floor
    assert row["total_floors"] == 18
    assert row["floor_band"] == band
    assert row["unit_price"] == unit_price
    assert row["total_price_wan"] == pytest.approx(total_wan)
    assert row["list_date"] == "2026-10-14"
    assert row["completeness"] == pytest.approx(completeness)
    assert row["agent_contact"] == contact
    assert row["title"]


def test_unit_price_derived_from_total_price(platform_items: dict[str, dict]) -> None:
    """平台只给总价时按 总价×10000/面积 反推单价：722.39 万 / 98㎡ → 73713 元/㎡。"""
    item = {key: value for key, value in platform_items["portal"].items() if key != "price_per_sqm"}
    row = parse_anjuke(item)
    assert row["unit_price"] == 73713
    assert row["total_price_wan"] == pytest.approx(722.39)
    assert row["area_sqm"] == 98


def test_total_price_derived_from_unit_price(platform_items: dict[str, dict]) -> None:
    """平台只给单价时按 单价×面积/10000 反推总价（2 位小数）：36306×90/10000 → 326.75。"""
    item = {key: value for key, value in platform_items["moments"].items() if key != "total_price_wan"}
    row = parse_moments(item)
    assert row["unit_price"] == 36306
    assert row["total_price_wan"] == pytest.approx(326.75)


def test_missing_area_declines_and_lowers_completeness(platform_items: dict[str, dict]) -> None:
    """面积缺失：area_sqm=None（不进均价），完整度 7/8 = 0.875，不拿 0 顶替。"""
    item = {key: value for key, value in platform_items["portal"].items() if key != "area"}
    row = parse_anjuke(item)
    assert row["area_sqm"] is None
    assert row["completeness"] == pytest.approx(0.875)
    # 面积缺失时无法用总价反推单价，但平台给了单价，仍然保留
    assert row["unit_price"] == 73713


def test_notice_platform_mm_dd_date(platform_items: dict[str, dict]) -> None:
    """门店群公告只有 MM-DD：按 YEAR_ANCHOR=2026 落到 2026-10-14。"""
    row = parse_notice(platform_items["notice"])
    assert row["list_date"] == "2026-10-14"
    assert row["floor"] == 15            # 「高楼层」+ 总 18 层 → 代表层 15
    assert row["floor_band"] == "高楼层"


def test_forum_platform_band_floor(platform_items: dict[str, dict]) -> None:
    """业主论坛只给「中楼层」+ 总层 18：落到 9 层，不是 18 层也不是 0。"""
    row = parse_forum(platform_items["forum"])
    assert row["floor"] == 9
    assert row["total_floors"] == 18
    assert row["agent_contact"] is None
    assert row["completeness"] == pytest.approx(0.875)


def test_lianjia_platform_exact_fields(platform_items: dict[str, dict]) -> None:
    """聚合站字段最全：完整度 1.0，面积/楼层/单价/总价/日期都直取。"""
    row = parse_lianjia(platform_items["aggregator"])
    assert row["completeness"] == pytest.approx(1.0)
    assert row["agent_name"] == "陈默"
    assert row["floor_band"] == "低楼层"
    assert row["raw"]["house_code"] == "LJ-100201"


# ---------------- 日期归一 ----------------

@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-10-24", "2026-10-24"),
        ("2026/10/24", "2026-10-24"),
        ("2026年10月24日 21:14", "2026-10-24"),
        ("2026-10-24 20:11", "2026-10-24"),
        ("10-24", "2026-10-24"),
        ("10月24日", "2026-10-24"),
        ("不是日期", None),
        ("", None),
        (None, None),
    ],
)
def test_to_date_formats(raw: str | None, expected: str | None) -> None:
    assert _to_date(raw) == expected
