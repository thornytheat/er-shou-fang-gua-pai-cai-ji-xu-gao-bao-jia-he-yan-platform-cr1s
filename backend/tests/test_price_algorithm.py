"""算法 2：小区×户型 稳健 z 检验（块统计 / 判定 / 置信度，纯函数）。"""
from __future__ import annotations

import pytest

from src.constants.limits import CONFIDENCE_WEIGHTS, MIN_SAMPLES_FOR_FLAG
from src.services.price_service import (
    block_stats,
    classify,
    confidence_score,
    deviation_pct,
    mad,
    median,
    robust_z,
)

# 真实 seed 的一个 8 条样本块（兰亭苑 三居，去重后主房源单价）
SEED_BLOCK: list[float] = [58000, 58900, 61200, 59000, 60200, 58300, 57500, 59500]
# 9 条样本，1 条明显虚高（90000）
HIGH_BLOCK: list[float] = [58000, 58500, 59000, 59500, 60000, 60500, 61000, 61500, 90000]
# 9 条样本，1 条明显虚低（30000）
LOW_BLOCK: list[float] = [30000, 59000, 59500, 60000, 60500, 61000, 61500, 62000, 62500]


# ---------------- 算法 B 正常路径 ----------------

def test_block_stats_real_sample_hand_computed() -> None:
    """8 条真实样本：中位 58,950 / MAD 800 / 均值 59,075 / 极差 6.28%。"""
    stats = block_stats(SEED_BLOCK)
    assert stats["sample_size"] == 8
    assert stats["median_price"] == pytest.approx(58950.0)
    assert stats["mad"] == pytest.approx(800.0)
    assert stats["mean_price"] == pytest.approx(59075.0)
    assert stats["min_price"] == pytest.approx(57500.0)
    assert stats["max_price"] == pytest.approx(61200.0)
    assert stats["spread_pct"] == pytest.approx(6.28)
    # 单个样本的稳健 z：0.6745*(61200-58950)/800
    assert robust_z(61200, 58950, 800) == pytest.approx(1.8970, abs=1e-4)
    assert deviation_pct(61200, 58950) == pytest.approx(3.8168, abs=1e-4)


def test_classify_high_hand_computed() -> None:
    """9 条样本里 1 条 90000：偏离 +50%、z=20.235、置信度 0.69。"""
    verdict = classify(90000, median_price=60000, spread=1000, sample_size=9, completeness=1.0)
    assert verdict["flag_type"] == "high"
    assert verdict["deviation_pct"] == pytest.approx(50.0)
    assert verdict["z_score"] == pytest.approx(20.235)
    # 0.40*min(1, 9/40) + 0.35*min(1, 20.235/6) + 0.25*1.0 = 0.09 + 0.35 + 0.25
    assert verdict["confidence"] == pytest.approx(0.69)
    assert verdict["reason"].startswith("偏离中位 +50.0%")


def test_classify_low_hand_computed() -> None:
    """9 条样本里 1 条 30000：偏离 -50.41%、z=-20.5723 → low。"""
    stats = block_stats(LOW_BLOCK)
    verdict = classify(
        30000,
        median_price=stats["median_price"],
        spread=stats["mad"],
        sample_size=stats["sample_size"],
        completeness=1.0,
    )
    assert verdict["flag_type"] == "low"
    assert verdict["deviation_pct"] == pytest.approx(-50.41)
    assert verdict["z_score"] == pytest.approx(-20.5723)
    assert verdict["confidence"] == pytest.approx(0.69)


# ---------------- 算法 B 边界 ----------------

def test_sample_too_small_degrades_to_none() -> None:
    """样本 7 条 < 8 条下限：不做判定，但偏离度仍如实返回给人工看。"""
    verdict = classify(90000, median_price=60000, spread=1000, sample_size=MIN_SAMPLES_FOR_FLAG - 1)
    assert verdict["flag_type"] is None
    assert verdict["z_score"] is None
    assert verdict["deviation_pct"] == pytest.approx(50.0)
    assert verdict["confidence"] == pytest.approx(0.0)
    assert "不足 8 条" in verdict["reason"]


def test_zero_variance_identical_prices_no_flag() -> None:
    """全相同单价零方差：MAD=0 → 稳健 z 无定义（None），偏离 0% → 不产生工单。"""
    stats = block_stats([60000] * 9)
    assert stats["mad"] == pytest.approx(0.0)
    assert stats["median_price"] == pytest.approx(60000.0)
    assert stats["spread_pct"] == pytest.approx(0.0)
    assert robust_z(60000, 60000, stats["mad"]) is None

    verdict = classify(60000, median_price=60000, spread=0.0, sample_size=9, completeness=1.0)
    assert verdict["flag_type"] is None
    assert verdict["deviation_pct"] == pytest.approx(0.0)
    assert verdict["z_score"] is None
    # 样本分 0.09 + z 分 0 + 完整度 0.25
    assert verdict["confidence"] == pytest.approx(0.34)


def test_zero_variance_outlier_degrades_to_uncertain() -> None:
    """MAD=0 但偏离 50%：z 不可用 → 只能落「待确认」，文案里不能出现 None。

    回归点：修复前这里 `f"{z_value:.2f}"` 会对 None 抛 TypeError → 接口 500。
    """
    stats = block_stats([60000] * 8 + [90000])
    assert stats["mad"] == pytest.approx(0.0)          # 8 条相同 + 1 条异常 → MAD 仍为 0
    assert stats["median_price"] == pytest.approx(60000.0)

    verdict = classify(90000, median_price=60000, spread=0.0, sample_size=9, completeness=1.0)
    assert verdict["flag_type"] == "uncertain"
    assert verdict["z_score"] is None
    assert verdict["deviation_pct"] == pytest.approx(50.0)
    assert verdict["confidence"] == pytest.approx(0.34)   # z 分按 0 计
    assert "不可用（MAD=0）" in verdict["reason"]
    assert "None" not in verdict["reason"]


def test_missing_unit_price_degrades() -> None:
    """单价缺失（面积缺失的挂牌同理）：不判定、置信度 0、文案说明不计入均价。"""
    verdict = classify(None, median_price=60000, spread=1000, sample_size=9)
    assert verdict["flag_type"] is None
    assert verdict["z_score"] is None
    assert verdict["deviation_pct"] is None
    assert verdict["confidence"] == pytest.approx(0.0)
    assert verdict["reason"] == "面积或单价缺失，不计入均价"


def test_block_stats_empty_and_all_missing() -> None:
    """空块 / 全是缺失值：样本 0，所有统计量 None，不拿 0 冒充。"""
    empty = block_stats([])
    assert empty["sample_size"] == 0
    for key in ("median_price", "mad", "mean_price", "min_price", "max_price", "spread_pct"):
        assert empty[key] is None
    assert block_stats([None, 0, 0])["sample_size"] == 0


def test_median_mad_edges() -> None:
    """中位数奇偶、空列表、MAD 零方差、z 的 spread<=0 都要明确返回。"""
    assert median([1, 2, 3, 4]) == pytest.approx(2.5)
    assert median([1, 2, 3]) == pytest.approx(2.0)
    assert median([]) is None
    assert mad([], None) is None
    assert mad([10, 10, 10], 10) == pytest.approx(0.0)
    assert robust_z(3, 1, 0) is None
    assert robust_z(3, 1, None) is None
    assert deviation_pct(10, 0) == pytest.approx(0.0)


# ---------------- 不变量 / 性质 ----------------

def test_confidence_weights_and_bounds() -> None:
    """置信度 = 0.40*样本 + 0.35*|z| + 0.25*完整度，满分封顶 1.0。"""
    assert sum(CONFIDENCE_WEIGHTS.values()) == pytest.approx(1.0)
    assert confidence_score(40, 6.0, 1.0) == pytest.approx(1.0)
    assert confidence_score(8, 3.0, 1.0) == pytest.approx(0.505)   # 0.08 + 0.175 + 0.25
    assert confidence_score(0, None, 0.0) == pytest.approx(0.0)
    assert confidence_score(9, None, 1.0) == pytest.approx(0.34)
    assert confidence_score(40, 6.0, 5.0) == pytest.approx(1.0)     # 完整度>1 被夹住


def test_confidence_monotonic_in_sample_and_z() -> None:
    """样本越多、|z| 越大，置信度不下降。"""
    assert confidence_score(40, 3.0, 1.0) > confidence_score(8, 3.0, 1.0)
    assert confidence_score(8, 6.0, 1.0) > confidence_score(8, 2.0, 1.0)
    assert confidence_score(8, -6.0, 1.0) == pytest.approx(confidence_score(8, 6.0, 1.0))


def test_confidence_ratio_in_unit_interval() -> None:
    """置信度与相似度都必须落在 [0,1]（枚举一批极端输入）。"""
    for sample in (0, 1, 8, 39, 40, 200):
        for z_value in (None, -30.0, -3.0, 0.0, 3.0, 30.0):
            for completeness in (0.0, 0.5, 1.0, 2.0):
                score = confidence_score(sample, z_value, completeness)
                assert 0.0 <= score <= 1.0
                assert score == pytest.approx(round(score, 4))


def test_flag_severity_monotonic_in_deviation() -> None:
    """越异常等级不降：50%/z20 → high；28% → uncertain；10% → 不判定。"""
    severe = classify(90000, median_price=60000, spread=1000, sample_size=9)
    border = classify(76800, median_price=60000, spread=1000, sample_size=9)
    normal = classify(66000, median_price=60000, spread=1000, sample_size=9)
    assert severe["flag_type"] == "high"
    assert border["flag_type"] == "uncertain"
    assert border["deviation_pct"] == pytest.approx(28.0)
    assert normal["flag_type"] is None
    assert normal["deviation_pct"] == pytest.approx(10.0)
    # 偏离度必须单调
    assert severe["deviation_pct"] > border["deviation_pct"] > normal["deviation_pct"]


def test_classify_symmetric_direction() -> None:
    """同一 |z|、同一 |偏离| 的高低两侧判定互为镜像，置信度相同。"""
    high = classify(90000, median_price=60000, spread=1000, sample_size=9, completeness=1.0)
    low = classify(30000, median_price=60000, spread=1000, sample_size=9, completeness=1.0)
    assert (high["flag_type"], low["flag_type"]) == ("high", "low")
    assert high["z_score"] == pytest.approx(-low["z_score"])
    assert high["deviation_pct"] == pytest.approx(-low["deviation_pct"])
    assert high["confidence"] == pytest.approx(low["confidence"])


def test_block_stats_deterministic() -> None:
    """同一样本两次统计结果相同（纯函数）。"""
    assert block_stats(HIGH_BLOCK) == block_stats(list(HIGH_BLOCK))
    assert block_stats(HIGH_BLOCK)["sample_size"] == 9
