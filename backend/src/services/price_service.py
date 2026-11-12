"""算法 2：小区×户型 稳健 z 检验与均价口径（纯函数）。

口径：
  med = 该小区×户型样本单价中位数
  MAD = median(|x_i - med|)
  z   = 0.6745 * (x - med) / MAD
  判定：样本 ≥ 8；|z| > 3 且 |偏离| > 30% -> high / low
        25% < |偏离| ≤ 30% -> uncertain（边界样本，交人工）
        面积缺失的挂牌不进入分组样本（unknown）
  置信度 = 0.40*样本量分 + 0.35*|z| 分 + 0.25*字段完整度
"""
from __future__ import annotations

from src.constants.enums import FlagType
from src.constants.limits import (
    CONFIDENCE_WEIGHTS,
    DEV_BORDER_PCT,
    DEV_FLAG_PCT,
    MIN_SAMPLES_FOR_FLAG,
    SAMPLE_FULL,
    Z_FULL,
    Z_THRESHOLD,
)


def median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    size = len(ordered)
    mid = size // 2
    if size % 2 == 1:
        return float(ordered[mid])
    return (float(ordered[mid - 1]) + float(ordered[mid])) / 2.0


def mad(values: list[float], center: float | None = None) -> float | None:
    if not values:
        return None
    center = median(values) if center is None else center
    deviations = [abs(float(value) - float(center)) for value in values]
    return median(deviations)


def robust_z(value: float, center: float, spread: float | None) -> float | None:
    if spread is None or spread <= 0:
        return None
    return 0.6745 * (float(value) - float(center)) / float(spread)


def block_stats(values: list[int | float]) -> dict:
    # 只收正单价：0 / 负数（解析噪声、占位值）不得混入中位数与 MAD
    numbers = [float(value) for value in values if value is not None and float(value) > 0]
    if not numbers:
        return {
            "sample_size": 0,
            "median_price": None,
            "mad": None,
            "mean_price": None,
            "min_price": None,
            "max_price": None,
            "spread_pct": None,
        }
    center = median(numbers)
    spread = mad(numbers, center)
    mean = sum(numbers) / len(numbers)
    return {
        "sample_size": len(numbers),
        "median_price": round(center, 2),
        "mad": round(spread, 2) if spread is not None else None,
        "mean_price": round(mean, 2),
        "min_price": round(min(numbers), 2),
        "max_price": round(max(numbers), 2),
        "spread_pct": round((max(numbers) - min(numbers)) / center * 100, 2) if center else None,
    }


def deviation_pct(value: float, center: float) -> float:
    if not center:
        return 0.0
    return (float(value) - float(center)) / float(center) * 100.0


def confidence_score(sample_size: int, z_value: float | None, completeness: float) -> float:
    sample_part = min(1.0, sample_size / SAMPLE_FULL)
    z_part = min(1.0, abs(z_value) / Z_FULL) if z_value is not None else 0.0
    score = (
        CONFIDENCE_WEIGHTS["sample"] * sample_part
        + CONFIDENCE_WEIGHTS["z"] * z_part
        + CONFIDENCE_WEIGHTS["completeness"] * max(0.0, min(1.0, completeness))
    )
    return round(score, 4)


def classify(
    unit_price: float | None,
    *,
    median_price: float | None,
    spread: float | None,
    sample_size: int,
    completeness: float = 1.0,
) -> dict:
    """单条挂牌的价格判定。返回 flag_type / z / 偏离度 / 置信度 / 说明。"""
    if unit_price is None or median_price is None:
        return {
            "flag_type": None,
            "z_score": None,
            "deviation_pct": None,
            "confidence": 0.0,
            "reason": "面积或单价缺失，不计入均价",
        }
    if sample_size < MIN_SAMPLES_FOR_FLAG:
        return {
            "flag_type": None,
            "z_score": None,
            "deviation_pct": round(deviation_pct(unit_price, median_price), 2),
            "confidence": 0.0,
            "reason": f"样本 {sample_size} 条，不足 {MIN_SAMPLES_FOR_FLAG} 条不做判定",
        }

    z_value = robust_z(unit_price, median_price, spread)
    dev = deviation_pct(unit_price, median_price)
    confidence = confidence_score(sample_size, z_value, completeness)
    abs_dev = abs(dev)
    abs_z = abs(z_value) if z_value is not None else 0.0
    # MAD=0（样本零方差）时稳健 z 无定义，文案里不能出现 "None"
    z_text = f"{z_value:.2f}" if z_value is not None else "不可用（MAD=0）"

    if abs_dev > DEV_FLAG_PCT and abs_z > Z_THRESHOLD:
        flag_type = FlagType.HIGH.value if dev > 0 else FlagType.LOW.value
        reason = (
            f"偏离中位 {dev:+.1f}%，稳健 z={z_text}（阈值 |z|>{Z_THRESHOLD:.0f} 且偏离>{DEV_FLAG_PCT:.0f}%）"
        )
    elif abs_dev > DEV_BORDER_PCT:
        flag_type = FlagType.UNCERTAIN.value
        reason = (
            f"偏离中位 {dev:+.1f}% 落在 {DEV_BORDER_PCT:.0f}%~{DEV_FLAG_PCT:.0f}% 边界带"
            f"（z={z_text}），需人工确认"
        )
    else:
        flag_type = None
        reason = f"偏离中位 {dev:+.1f}%，在正常区间"

    return {
        "flag_type": flag_type,
        "z_score": round(z_value, 4) if z_value is not None else None,
        "deviation_pct": round(dev, 2),
        "confidence": confidence,
        "reason": reason,
    }
