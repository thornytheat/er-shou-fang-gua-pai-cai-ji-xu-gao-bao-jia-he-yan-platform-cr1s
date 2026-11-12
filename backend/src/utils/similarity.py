"""房源指纹：规范化 + 加权相似度（纯函数，无 DB / 无随机）。

口径（与 constants/limits.py 一一对应）：
  1. 规范化：小区别名表、户型别名、面积取整到 1㎡、楼层带归一
  2. blocking key = 小区 × 户型（只在这两个维度相同的候选集里比）
  3. 加权相似 = 面积 0.30 + 楼层 0.20 + 标题 Jaccard 0.25 + 单价接近度 0.25
  4. ≥ 0.82 连边，交给并查集聚类
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

from src.constants.limits import (
    AREA_TOL_SQM,
    FLOOR_TOL,
    PRICE_TOL_PCT,
    SIM_THRESHOLD,
    SIM_WEIGHTS,
)

# ---------- 小区别名表（人工维护，研究组口径） ----------
COMMUNITY_ALIASES: dict[str, str] = {
    "兰亭苑": "兰亭苑",
    "兰亭苑小区": "兰亭苑",
    "兰亭苑花园": "兰亭苑",
    "兰亭苑一期": "兰亭苑",
    "阳光里": "阳光里",
    "阳光里家园": "阳光里",
    "阳光里北区": "阳光里",
    "云栖湾": "云栖湾",
    "云栖湾公馆": "云栖湾",
    "云栖湾二期": "云栖湾",
    "静安里": "静安里",
    "静安里公寓": "静安里",
    "静安里南苑": "静安里",
}

CANONICAL_COMMUNITIES: list[str] = ["兰亭苑", "阳光里", "云栖湾", "静安里"]

_LAYOUT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(3|三)\s*(室|房|居)"), "三居"),
    (re.compile(r"(2|二|两)\s*(室|房|居)"), "两居"),
    (re.compile(r"(1|一)\s*(室|房|居)"), "一居"),
    (re.compile(r"开间|单间|studio", re.I), "一居"),
]

_PUNCT = re.compile(r"[\s\-_/\\|｜,，。·:：;；()（）\[\]【】<>《》\"'“”‘’!！?？~～*#]+")
_NUM_TOKEN = re.compile(r"[0-9]+(?:\.[0-9]+)?|[a-z]+")
_CJK = re.compile(r"[\u4e00-\u9fff]")
# 「共18层 / 总18层」里的数字是总层数，不是当前层，必须先摘掉再找层号
_TOTAL_FLOOR_HINT = re.compile(r"[（(]?\s*(?:共|总)\s*(\d+)\s*层\s*[）)]?")


def normalize_text(raw: str | None) -> str:
    if not raw:
        return ""
    text = unicodedata.normalize("NFKC", str(raw)).strip().lower()
    text = _PUNCT.sub("", text)
    return text


def normalize_community(raw: str | None) -> str:
    """小区别名 -> 规范名；未收录的原样返回（去噪后）。"""
    text = normalize_text(raw)
    for alias, canonical in COMMUNITY_ALIASES.items():
        if normalize_text(alias) == text:
            return canonical
    for alias, canonical in COMMUNITY_ALIASES.items():
        if normalize_text(alias) and normalize_text(alias) in text:
            return canonical
    return raw.strip() if raw else "未知小区"


def normalize_layout(raw: str | None) -> str:
    """户型文本 -> 一居 / 两居 / 三居。"""
    text = unicodedata.normalize("NFKC", str(raw or "")).strip()
    for pattern, canonical in _LAYOUT_PATTERNS:
        if pattern.search(text):
            return canonical
    return text or "未知户型"


def normalize_area(raw: float | int | str | None) -> int | None:
    """面积取整到 1㎡；缺失/不可解析返回 None（后续不计入均价）。"""
    if raw is None or raw == "":
        return None
    try:
        value = float(str(raw).replace("㎡", "").replace("平米", "").replace("平", "").strip())
    except (TypeError, ValueError):
        return None
    if value <= 0 or value > 1000:
        return None
    return int(round(value))


def normalize_floor(raw: float | int | str | None, total_floors: int | None) -> int | None:
    """楼层号归一：'9/18'、'9'、'中楼层(共18层)' 都落到具体层。"""
    if raw is None or raw == "":
        return None
    if isinstance(raw, (int, float)):
        return int(raw)
    text = unicodedata.normalize("NFKC", str(raw))
    match = re.search(r"(\d+)\s*/\s*(\d+)", text)
    if match:
        return int(match.group(1))
    # 「中楼层(共18层)」：数字属于总层数，当前层只能由楼层带推出来
    hinted_total = total_floors
    floor_hint = _TOTAL_FLOOR_HINT.search(text)
    if floor_hint:
        if hinted_total is None:
            hinted_total = int(floor_hint.group(1))
        text = _TOTAL_FLOOR_HINT.sub("", text)
    match = re.search(r"(\d+)", text)
    if match:
        return int(match.group(1))
    band = floor_band(raw)
    return band_to_floor(band, hinted_total)


def floor_band(raw: float | int | str | None, total_floors: int | None = None) -> str | None:
    """楼层带：低楼层 / 中楼层 / 高楼层；拿不到就按层号分三段。"""
    if raw is None or raw == "":
        return None
    text = unicodedata.normalize("NFKC", str(raw))
    if "低" in text:
        return "低楼层"
    if "中" in text:
        return "中楼层"
    if "高" in text or "顶" in text:
        return "高楼层"
    floor = None
    if isinstance(raw, (int, float)):
        floor = int(raw)
    else:
        match = re.search(r"(\d+)", text)
        floor = int(match.group(1)) if match else None
    if floor is None:
        return None
    total = total_floors or 18
    ratio = floor / max(total, 1)
    if ratio <= 0.34:
        return "低楼层"
    if ratio <= 0.67:
        return "中楼层"
    return "高楼层"


def band_to_floor(band: str | None, total_floors: int | None) -> int | None:
    """楼层带 -> 代表层号（低 3 / 中 9 / 高 15，按总层等比缩放）。"""
    if not band:
        return None
    total = total_floors or 18
    ratio = {"低楼层": 0.18, "中楼层": 0.5, "高楼层": 0.82}.get(band, 0.5)
    value = int(round(total * ratio))
    return max(1, min(value, total - 1))


def title_tokens(title: str | None) -> set[str]:
    """标题 token 集：CJK 二元组 + 数字/字母词。"""
    text = normalize_text(title)
    tokens: set[str] = set()
    for match in _NUM_TOKEN.finditer(text):
        tokens.add(match.group(0))
    chars = [ch for ch in text if _CJK.match(ch)]
    for index in range(len(chars) - 1):
        tokens.add(chars[index] + chars[index + 1])
    tokens.update(chars)
    return tokens


def jaccard(left: str | None, right: str | None) -> float:
    a, b = title_tokens(left), title_tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def area_similarity(area_a: int | None, area_b: int | None) -> float:
    if area_a is None or area_b is None:
        return 0.0
    gap = abs(area_a - area_b)
    return max(0.0, 1.0 - gap / AREA_TOL_SQM)


def floor_similarity(floor_a: int | None, floor_b: int | None) -> float:
    if floor_a is None or floor_b is None:
        return 0.0
    gap = abs(floor_a - floor_b)
    return max(0.0, 1.0 - gap / FLOOR_TOL)


def price_similarity(price_a: float | None, price_b: float | None) -> float:
    if not price_a or not price_b:
        return 0.0
    mean = (price_a + price_b) / 2.0
    tolerance = max(mean * PRICE_TOL_PCT, 1.0)
    return max(0.0, 1.0 - abs(price_a - price_b) / tolerance)


def similarity_breakdown(left: dict, right: dict) -> dict:
    """返回四个分量 + 加权总分 + 是否连边。"""
    parts = {
        "area": area_similarity(left.get("area_sqm"), right.get("area_sqm")),
        "floor": floor_similarity(left.get("floor"), right.get("floor")),
        "title": jaccard(left.get("title"), right.get("title")),
        "price": price_similarity(float(left.get("unit_price") or 0), float(right.get("unit_price") or 0)),
    }
    total = sum(parts[key] * SIM_WEIGHTS[key] for key in SIM_WEIGHTS)
    return {
        "components": {key: round(value, 4) for key, value in parts.items()},
        "score": round(total, 4),
        "linked": total >= SIM_THRESHOLD,
    }


class UnionFind:
    """并查集：路径压缩 + 按秩合并。"""

    def __init__(self, size: int) -> None:
        self.parent = list(range(size))
        self.rank = [0] * size

    def find(self, node: int) -> int:
        root = node
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[node] != root:
            self.parent[node], node = root, self.parent[node]
        return root

    def union(self, left: int, right: int) -> bool:
        a, b = self.find(left), self.find(right)
        if a == b:
            return False
        if self.rank[a] < self.rank[b]:
            a, b = b, a
        self.parent[b] = a
        if self.rank[a] == self.rank[b]:
            self.rank[a] += 1
        return True

    def groups(self) -> dict[int, list[int]]:
        buckets: dict[int, list[int]] = {}
        for index in range(len(self.parent)):
            buckets.setdefault(self.find(index), []).append(index)
        return buckets


def blocking_key(row: dict) -> str:
    return f"{row.get('community')}::{row.get('layout')}"


def block_rows(rows: Iterable[dict]) -> dict[str, list[int]]:
    buckets: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        buckets.setdefault(blocking_key(row), []).append(index)
    return buckets
