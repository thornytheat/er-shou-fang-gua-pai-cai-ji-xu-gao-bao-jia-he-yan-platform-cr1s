"""五个采集平台的字段解析（纯函数，无 IO）。

真实采集中这里是 HTML/JSON 抽取层；演示环境把平台页面固化成
fixtures/platforms.json 的确定性快照，本模块负责把各自的字段口径
（单价单位、楼层写法、日期写法、面积精度）统一成 Listing 结构，
这样「跨平台重复挂牌」才有可比的指纹。
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from src.utils.similarity import (
    floor_band,
    normalize_area,
    normalize_community,
    normalize_floor,
    normalize_layout,
)

YEAR_ANCHOR = 2026


def _to_date(raw: str | None) -> str | None:
    """把 2026-10-24 / 2026/10/24 / 2026年10月24日 21:14 / 10-24 统一成 ISO 日期。"""
    if not raw:
        return None
    text = str(raw).strip()
    match = re.search(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})", text)
    if match:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3))).isoformat()
    match = re.search(r"^(\d{1,2})[-/月](\d{1,2})", text)
    if match:
        return date(YEAR_ANCHOR, int(match.group(1)), int(match.group(2))).isoformat()
    return None


def _to_float(raw) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    match = re.search(r"-?\d+(?:\.\d+)?", str(raw).replace(",", ""))
    return float(match.group(0)) if match else None


def _completeness(row: dict) -> float:
    """字段完整度：面积/楼层/总层/单价/总价/标题/挂牌日/联系方式 各占 1/8。"""
    fields = ["area_sqm", "floor", "total_floors", "unit_price", "title", "list_date"]
    filled = sum(1 for key in fields if row.get(key) not in (None, "", 0))
    filled += 1 if row.get("agent_contact") else 0
    filled += 1 if row.get("total_price_wan") else 0
    return round(filled / 8.0, 4)


def _assemble(**kwargs) -> dict:
    area = normalize_area(kwargs.get("area_raw"))
    total_floors = kwargs.get("total_floors")
    floor = normalize_floor(kwargs.get("floor_raw"), total_floors)
    band = floor_band(kwargs.get("floor_raw"), total_floors)
    unit_price = _to_float(kwargs.get("unit_price_raw"))
    total_raw = _to_float(kwargs.get("total_price_raw"))
    if unit_price is None and area and total_raw:
        unit_price = round(total_raw * 10000 / area)
    unit_price = int(round(unit_price)) if unit_price else None
    total_wan = total_raw if total_raw is not None else (
        round(unit_price * area / 10000, 2) if unit_price and area else None
    )
    row = {
        "source_listing_no": kwargs["source_listing_no"],
        "community": normalize_community(kwargs.get("community")),
        "layout": normalize_layout(kwargs.get("layout_raw")),
        "area_sqm": area,
        "floor": floor,
        "total_floors": total_floors,
        "floor_band": band,
        "unit_price": unit_price,
        "total_price_wan": total_wan,
        "list_date": _to_date(kwargs.get("list_date_raw")),
        "title": kwargs.get("title") or "",
        "agent_name": kwargs.get("agent_name"),
        "agent_contact": kwargs.get("agent_contact"),
        "raw": kwargs.get("raw") or {},
    }
    row["completeness"] = _completeness(row)
    return row


def parse_lianjia(item: dict) -> dict:
    return _assemble(
        source_listing_no=item["house_code"],
        community=item["resblock"],
        layout_raw=item.get("huxing"),
        area_raw=item.get("build_area"),
        floor_raw=item.get("floor_no"),
        total_floors=item.get("total_floors"),
        unit_price_raw=item.get("unit_price_yuan"),
        total_price_raw=item.get("total_price_wan"),
        list_date_raw=item.get("online_date"),
        title=item.get("title"),
        agent_name=item.get("agent"),
        agent_contact=item.get("phone"),
        raw=item,
    )


def parse_anjuke(item: dict) -> dict:
    floor_text = item.get("floor") or ""
    total = None
    match = re.search(r"/\s*(\d+)", str(floor_text))
    if match:
        total = int(match.group(1))
    return _assemble(
        source_listing_no=item["info_id"],
        community=item["community"],
        layout_raw=item.get("huxing"),
        area_raw=item.get("area"),
        floor_raw=floor_text,
        total_floors=total,
        unit_price_raw=item.get("price_per_sqm"),
        total_price_raw=item.get("total_price_wan"),
        list_date_raw=item.get("pub_date"),
        title=item.get("subject"),
        agent_name=item.get("broker"),
        agent_contact=item.get("tel"),
        raw=item,
    )


def parse_forum(item: dict) -> dict:
    return _assemble(
        source_listing_no=item["thread_id"],
        community=item["xiaoqu"],
        layout_raw=item.get("huxing"),
        area_raw=item.get("mianji"),
        floor_raw=item.get("louceng"),
        total_floors=item.get("zongceng"),
        unit_price_raw=item.get("danjia"),
        total_price_raw=item.get("total_price_wan"),
        list_date_raw=item.get("post_date"),
        title=item.get("subject"),
        agent_name=item.get("poster"),
        agent_contact=None,
        raw=item,
    )


def parse_moments(item: dict) -> dict:
    return _assemble(
        source_listing_no=item["archive_id"],
        community=item["community"],
        layout_raw=item.get("layout"),
        area_raw=item.get("area_sqm"),
        floor_raw=item.get("floor_no"),
        total_floors=item.get("total_floors"),
        unit_price_raw=item.get("unit_price"),
        total_price_raw=item.get("total_price_wan"),
        list_date_raw=item.get("captured_at"),
        title=item.get("caption"),
        agent_name=item.get("agent"),
        agent_contact=item.get("phone"),
        raw=item,
    )


def parse_notice(item: dict) -> dict:
    return _assemble(
        source_listing_no=item["notice_id"],
        community=item["xiaoqu"],
        layout_raw=item.get("huxing"),
        area_raw=item.get("mianji"),
        floor_raw=item.get("louceng_desc"),
        total_floors=item.get("zongceng"),
        unit_price_raw=item.get("danjia"),
        total_price_raw=item.get("total_price_wan"),
        list_date_raw=item.get("riqi"),
        title=item.get("text"),
        agent_name=item.get("dianzhang"),
        agent_contact=None,
        raw=item,
    )


PARSERS = {
    "aggregator": parse_lianjia,
    "portal": parse_anjuke,
    "forum": parse_forum,
    "moments": parse_moments,
    "notice": parse_notice,
}


def parse_item(platform_kind: str, item: dict) -> dict:
    parser = PARSERS.get(platform_kind)
    if parser is None:
        raise ValueError(f"unknown platform kind: {platform_kind}")
    return parser(item)
