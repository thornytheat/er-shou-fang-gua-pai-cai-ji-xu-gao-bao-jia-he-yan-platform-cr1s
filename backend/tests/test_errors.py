"""异常输入：要么明确抛异常，要么明确降级为 None，不许静默返回脏值。"""
from __future__ import annotations

import pytest

from src.services.parsers import _to_date, parse_item, parse_lianjia
from src.services.price_service import block_stats, classify
from src.utils.similarity import normalize_area, normalize_floor


def test_unknown_platform_raises() -> None:
    """未知平台形态：明确 ValueError，而不是当成某个默认解析器静默解析。"""
    with pytest.raises(ValueError, match="unknown platform kind: 58同城"):
        parse_item("58同城", {})


def test_missing_natural_key_raises() -> None:
    """缺少自然键（house_code）时明确 KeyError，避免写入无主键的脏行。"""
    with pytest.raises(KeyError, match="house_code"):
        parse_lianjia({"resblock": "云栖湾"})


def test_unparsable_area_degrades_to_none() -> None:
    """面积是中文/乱码：降级 None（不进均价），不返回 0、不抛异常。"""
    assert normalize_area("九十八平米") is None
    assert normalize_area("约 98 平") is None      # 前缀「约 」导致 float 解析失败 → 降级
    assert normalize_area("98㎡") == 98


def test_invalid_calendar_date_raises() -> None:
    """2026-13-45 这种不合法的日历日期必须报错（由 run_ingest 的 per-source 兜底）。

    已知口径：这里选择「明确异常」而不是静默返回 None，避免把 13 月悄悄写成别的月份。
    """
    with pytest.raises(ValueError, match="month must be in 1..12"):
        _to_date("2026-13-45")


def test_negative_and_overflow_price_block_is_empty() -> None:
    """全 0 / 负单价样本：块统计样本数为 0，判定直接降级，不产生 high/low。"""
    stats = block_stats([0, -1, -58000])
    assert stats["sample_size"] == 0
    assert stats["median_price"] is None
    verdict = classify(0, median_price=stats["median_price"], spread=stats["mad"], sample_size=0)
    assert verdict["flag_type"] is None
    assert verdict["confidence"] == pytest.approx(0.0)


def test_floor_out_of_range_input_does_not_crash() -> None:
    """异常楼层文本：楼层带能兜住就给代表层，兜不住就给 None（不抛异常）。"""
    assert normalize_floor("顶层", 18) == 15        # 落入高楼层带 → round(18*0.82)
    assert normalize_floor("地下-2", 18) == 2       # 只认数字，负号被忽略但不会抛
    assert normalize_floor("无", 18) is None
