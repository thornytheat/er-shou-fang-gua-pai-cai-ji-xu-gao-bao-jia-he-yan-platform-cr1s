"""算法 1 的规范化与加权相似度（纯函数，手算期望值）。"""
from __future__ import annotations

import pytest

from src.constants.limits import SIM_THRESHOLD, SIM_WEIGHTS
from src.utils.similarity import (
    area_similarity,
    band_to_floor,
    block_rows,
    blocking_key,
    floor_band,
    floor_similarity,
    jaccard,
    normalize_area,
    normalize_community,
    normalize_floor,
    normalize_layout,
    normalize_text,
    price_similarity,
    similarity_breakdown,
    title_tokens,
)


# ---------------- 算法 A 正常路径 ----------------

def test_identical_rows_score_one(row_a: dict) -> None:
    """同一条挂牌和自己比：四个分量全 1.0，总分 1.0，必然连边。"""
    result = similarity_breakdown(row_a, dict(row_a))
    assert result["components"]["area"] == pytest.approx(1.0)
    assert result["components"]["floor"] == pytest.approx(1.0)
    assert result["components"]["title"] == pytest.approx(1.0)
    assert result["components"]["price"] == pytest.approx(1.0)
    assert result["score"] == pytest.approx(1.0)
    assert result["linked"] is True


def test_cross_platform_same_house_hand_computed(row_a: dict, row_b: dict) -> None:
    """真实 seed 的跨平台同一套房：0.874 分（0.30+0.20+0.25*0.6585+0.25*0.8376）。"""
    result = similarity_breakdown(row_a, row_b)
    assert result["components"]["area"] == pytest.approx(1.0)          # 140 vs 140
    assert result["components"]["floor"] == pytest.approx(1.0)         # 3 vs 3
    assert result["components"]["title"] == pytest.approx(0.6585, abs=1e-4)
    assert result["components"]["price"] == pytest.approx(0.8376, abs=1e-4)
    assert result["score"] == pytest.approx(0.8740, abs=1e-4)
    # 总分必须等于分量的加权和，而不是另算一套口径
    assert result["score"] == pytest.approx(
        sum(result["components"][key] * SIM_WEIGHTS[key] for key in SIM_WEIGHTS), abs=1e-4
    )
    assert result["score"] > SIM_THRESHOLD
    assert result["linked"] is True


def test_different_house_does_not_link(row_a: dict, seed_rows: list[dict]) -> None:
    """户型相同但面积/楼层/单价都不同 → 0.083 分，不连边。"""
    other = seed_rows[2]
    result = similarity_breakdown(row_a, other)
    assert result["components"]["area"] == pytest.approx(0.0)     # 140 vs 90，差 50㎡
    assert result["components"]["floor"] == pytest.approx(0.0)    # 3 vs 12，差 9 层
    assert result["components"]["price"] == pytest.approx(0.0)    # 44419 vs 70000，超出 8% 容差
    assert result["score"] == pytest.approx(0.0833, abs=1e-4)
    assert result["linked"] is False


def test_punctuation_variant_stays_jaccard_one() -> None:
    """同一标题的两种写法（空格/全角竖线）规范化后 token 完全一致。"""
    left = "云栖湾 3室2厅 140㎡ 低楼层 精装 满五 近地铁"
    right = "云栖湾3室2厅140㎡｜低楼层｜精装｜满五｜近地铁"
    assert normalize_text(left) == normalize_text(right)
    assert jaccard(left, right) == pytest.approx(1.0)


# ---------------- 算法 A 边界 ----------------

def test_area_similarity_tolerance_boundary() -> None:
    """面积容差 1㎡：相等 1.0，差 1㎡ 直接 0.0（不允许负分）。"""
    assert area_similarity(98, 98) == pytest.approx(1.0)
    assert area_similarity(98, 99) == pytest.approx(0.0)
    assert area_similarity(98, 104) == pytest.approx(0.0)
    assert area_similarity(None, 98) == pytest.approx(0.0)


def test_floor_similarity_tolerance_boundary() -> None:
    """楼层容差 4 层：差 1 层 0.75，差 4 层 0.0，缺失 0.0。"""
    assert floor_similarity(9, 9) == pytest.approx(1.0)
    assert floor_similarity(9, 10) == pytest.approx(0.75)
    assert floor_similarity(9, 13) == pytest.approx(0.0)
    assert floor_similarity(9, 20) == pytest.approx(0.0)
    assert floor_similarity(None, 9) == pytest.approx(0.0)


def test_price_similarity_hand_computed() -> None:
    """单价容差 = 均价 × 8%：40000 vs 42800 = 1 - 2800/3312。"""
    assert price_similarity(40000, 42800) == pytest.approx(0.15459, abs=1e-5)
    assert price_similarity(40000, 40000) == pytest.approx(1.0)
    # 差 16% 已越过容差 → 0.0（不是负数）
    assert price_similarity(40000, 46400) == pytest.approx(0.0)
    assert price_similarity(0, 50000) == pytest.approx(0.0)
    assert price_similarity(None, 50000) == pytest.approx(0.0)


def test_missing_fields_degrade_to_zero(seed_rows: list[dict]) -> None:
    """面积/楼层/单价全缺：四个分量都退化成 0，不报错、不静默算成 1。"""
    left = {**seed_rows[0], "area_sqm": None, "floor": None, "unit_price": None, "title": ""}
    right = {**seed_rows[1], "area_sqm": None, "floor": None, "unit_price": None, "title": ""}
    result = similarity_breakdown(left, right)
    assert result["components"] == {"area": 0.0, "floor": 0.0, "title": 0.0, "price": 0.0}
    assert result["score"] == pytest.approx(0.0)
    assert result["linked"] is False


def test_title_tokens_and_jaccard_hand_computed() -> None:
    """'云栖湾三居' 9 个 token、'云栖湾三居精装' 13 个，交集 9 → 9/13。"""
    assert len(title_tokens("云栖湾三居")) == 9
    assert len(title_tokens("云栖湾三居精装")) == 13
    assert jaccard("云栖湾三居", "云栖湾三居精装") == pytest.approx(0.6923, abs=1e-4)
    assert jaccard("", "云栖湾三居") == pytest.approx(0.0)
    assert jaccard(None, None) == pytest.approx(0.0)


def test_unknown_block_is_its_own_group(seed_rows: list[dict]) -> None:
    """blocking key = 小区::户型；不同户型即使面积相同也不在同一个候选块。"""
    rows = [dict(seed_rows[0]), {**seed_rows[1], "layout": "两居"}]
    blocks = block_rows(rows)
    assert list(blocks) == ["云栖湾::三居", "云栖湾::两居"]
    assert blocks["云栖湾::三居"] == [0]
    assert blocks["云栖湾::两居"] == [1]
    assert blocking_key(rows[0]) == "云栖湾::三居"


# ---------------- 归一 / 解析工具 ----------------

@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("兰亭苑小区", "兰亭苑"),
        ("兰亭苑一期", "兰亭苑"),
        ("阳光里家园", "阳光里"),
        ("云栖湾二期", "云栖湾"),
        (" 静安里南苑 ", "静安里"),
        ("翡翠城", "翡翠城"),          # 未收录的别名原样返回
        (None, "未知小区"),
        ("", "未知小区"),
    ],
)
def test_normalize_community(raw: str | None, expected: str) -> None:
    assert normalize_community(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("3室2厅", "三居"),
        ("两居(按套内计)", "两居"),
        ("2室2厅", "两居"),
        ("1室1厅", "一居"),
        ("开间", "一居"),
        ("STUDIO", "一居"),
        ("", "未知户型"),
        (None, "未知户型"),
    ],
)
def test_normalize_layout(raw: str | None, expected: str) -> None:
    assert normalize_layout(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("140.0", 140),
        ("98㎡", 98),
        ("124平米", 124),
        (89.4, 89),
        (89.6, 90),
        (1000, 1000),
        (1000.5, None),   # 越界 → 明确 None，不进均价
        (-3, None),
        (0, None),
        ("", None),
        ("abc", None),
        (None, None),
    ],
)
def test_normalize_area(raw: object, expected: int | None) -> None:
    assert normalize_area(raw) == expected


@pytest.mark.parametrize(
    ("raw", "total", "expected_floor", "expected_band"),
    [
        (9, 18, 9, "中楼层"),
        ("9/18", None, 9, "中楼层"),
        ("15/18", None, 15, "高楼层"),
        ("中楼层", 18, 9, "中楼层"),
        ("高楼层", 18, 15, "高楼层"),
        # 平台只给「中楼层(共18层)」时，18 是总层数，不能当成当前层
        ("中楼层(共18层)", None, 9, "中楼层"),
        ("中楼层(共18层)", 18, 9, "中楼层"),
        ("高楼层(共18层)", None, 15, "高楼层"),
        ("低楼层(共18层)", 18, 3, "低楼层"),
        (None, 18, None, None),
        ("", 18, None, None),
    ],
)
def test_normalize_floor_and_band(
    raw: object, total: int | None, expected_floor: int | None, expected_band: str | None
) -> None:
    assert normalize_floor(raw, total) == expected_floor
    assert floor_band(raw, total) == expected_band


def test_floor_band_thresholds() -> None:
    """楼层带按 总层数 三等分：≤34% 低、≤67% 中、其余高。"""
    assert floor_band(6, 18) == "低楼层"    # 0.333
    assert floor_band(7, 18) == "中楼层"    # 0.389
    assert floor_band(12, 18) == "中楼层"   # 0.667
    assert floor_band(13, 18) == "高楼层"   # 0.722
    assert floor_band("顶楼", 18) == "高楼层"
    assert band_to_floor("低楼层", 33) == 6     # round(33*0.18) = 6
    assert band_to_floor("中楼层", 18) == 9
    assert band_to_floor("高楼层", 18) == 15
    assert band_to_floor(None, 18) is None
