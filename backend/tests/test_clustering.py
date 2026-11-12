"""算法 1 的并查集聚类：build_clusters（纯函数）。"""
from __future__ import annotations

import json

import pytest

from src.services.fingerprint_service import build_clusters


def _ids(cluster: dict) -> list[int]:
    return sorted(cluster["member_ids"])


# ---------------- 算法 A 正常路径 ----------------

def test_real_slice_two_clusters(seed_rows: list[dict]) -> None:
    """真实 seed 切片：两条同一套房（0.874）连边，第三条面积/楼层差太远独立。"""
    result = build_clusters(seed_rows)
    assert result["edge_count"] == 1
    assert result["pair_count"] == 3          # C(3,2)，同一 blocking key 内两两比较
    assert result["dedup_count"] == 2
    assert result["duplicate_clusters"] == 1
    assert result["singletons"] == 1
    assert result["member_total"] == 3

    duplicate = next(cluster for cluster in result["clusters"] if cluster["is_duplicate"])
    assert _ids(duplicate) == [701, 702]
    # 主房源 = 挂牌最早（2026-10-12），不是字段最全的那条（10-14）
    assert duplicate["primary_id"] == 702
    assert duplicate["member_count"] == 2
    assert duplicate["platform_count"] == 2
    assert duplicate["min_similarity"] == pytest.approx(0.874, abs=1e-4)
    assert duplicate["max_similarity"] == pytest.approx(0.874, abs=1e-4)
    assert duplicate["avg_unit_price"] == 44710      # round((44419+45000)/2)

    singleton = next(cluster for cluster in result["clusters"] if not cluster["is_duplicate"])
    assert _ids(singleton) == [703]
    assert singleton["min_similarity"] is None
    assert singleton["max_similarity"] is None
    assert singleton["platform_count"] == 1


def test_three_identical_rows_one_cluster() -> None:
    """三条除 id/来源外完全相同的挂牌 → 一个 3 成员簇，两两相似度 1.0。"""
    rows = [
        {
            "id": 801 + offset,
            "source_id": offset + 1,
            "community": "兰亭苑",
            "layout": "三居",
            "area_sqm": 120,
            "floor": 6,
            "title": "兰亭苑 3室2厅 120㎡ 中楼层 满五唯一",
            "unit_price": 58900,
            "list_date": "2026-10-10",
            "completeness": 1.0,
        }
        for offset in range(3)
    ]
    result = build_clusters(rows)
    assert result["dedup_count"] == 1
    assert result["pair_count"] == 3
    assert result["edge_count"] == 2          # 并查集第三条边已被前两条并掉
    cluster = result["clusters"][0]
    assert _ids(cluster) == [801, 802, 803]
    assert cluster["member_count"] == 3
    assert cluster["platform_count"] == 3
    assert cluster["avg_unit_price"] == 58900
    assert cluster["min_similarity"] == pytest.approx(1.0)
    assert cluster["max_similarity"] == pytest.approx(1.0)


# ---------------- 算法 A 边界 ----------------

def test_empty_input_returns_zeros() -> None:
    """空输入：不抛异常，各项计数为 0（返回结构与非空分支一致）。"""
    result = build_clusters([])
    assert result["clusters"] == []
    assert result["edge_count"] == 0
    assert result["pair_count"] == 0
    assert result["dedup_count"] == 0
    assert result["duplicate_clusters"] == 0
    assert result["member_total"] == 0
    assert result["singletons"] == 0


def test_single_row_is_singleton(seed_rows: list[dict]) -> None:
    result = build_clusters([seed_rows[0]])
    assert result["dedup_count"] == 1
    assert result["duplicate_clusters"] == 0
    assert result["pair_count"] == 0
    cluster = result["clusters"][0]
    assert cluster["member_ids"] == [701]
    assert cluster["member_count"] == 1
    assert cluster["primary_id"] == 701
    assert cluster["is_duplicate"] is False
    assert cluster["min_similarity"] is None
    assert cluster["area_sqm"] == 140


def test_missing_area_rows_never_merge(seed_rows: list[dict]) -> None:
    """面积缺失的挂牌不参与两两比较（无法比较面积），各自独占一簇。"""
    rows = [
        {**seed_rows[0], "id": 901, "source_id": 1, "area_sqm": None},
        {**seed_rows[1], "id": 902, "source_id": 4, "area_sqm": None},
        {**seed_rows[2], "id": 903, "source_id": 3, "area_sqm": None},
    ]
    result = build_clusters(rows)
    assert result["pair_count"] == 0
    assert result["edge_count"] == 0
    assert result["dedup_count"] == 3
    assert result["singletons"] == 3
    assert result["member_total"] == 3


def test_threshold_monotonic(seed_rows: list[dict]) -> None:
    """阈值越高连边越少：0.90 断开 0.874 的那一对，0.80/0.86 连上。"""
    strict = build_clusters(seed_rows, threshold=0.90)
    default = build_clusters(seed_rows, threshold=0.86)
    loose = build_clusters(seed_rows, threshold=0.80)
    assert strict["edge_count"] == 0
    assert strict["dedup_count"] == 3
    assert default["edge_count"] == 1
    assert default["dedup_count"] == 2
    assert loose["edge_count"] == 1
    assert loose["dedup_count"] == 2


def test_primary_prefers_earliest_then_completeness_then_id() -> None:
    """主房源排序键：挂牌最早 → 字段最全 → id 最小。"""
    base = {
        "source_id": 1,
        "community": "阳光里",
        "layout": "两居",
        "area_sqm": 88,
        "floor": 9,
        "title": "阳光里 两居 88㎡ 中楼层 精装",
        "unit_price": 62000,
        "completeness": 0.5,
    }
    rows = [
        {**base, "id": 11, "list_date": "2026-10-20", "completeness": 1.0},
        {**base, "id": 12, "list_date": "2026-10-18", "completeness": 0.5},
        {**base, "id": 13, "list_date": "2026-10-18", "completeness": 0.875},
        {**base, "id": 14, "list_date": "2026-10-18", "completeness": 0.875},
    ]
    result = build_clusters(rows)
    assert result["dedup_count"] == 1
    cluster = result["clusters"][0]
    # 10-18 三条里 completeness 0.875 的两条 → id 小的 13 胜出
    assert cluster["primary_id"] == 13
    assert _ids(cluster) == [11, 12, 13, 14]


# ---------------- 不变量 / 性质 ----------------

def test_count_conservation(seed_rows: list[dict]) -> None:
    """计数守恒：成员总数 = 输入条数；非重复簇 + 单条簇 = 去重后条数；连边 ≤ 比较次数。"""
    result = build_clusters(seed_rows)
    assert result["member_total"] == len(seed_rows)
    assert result["singletons"] + result["duplicate_clusters"] == result["dedup_count"]
    assert result["edge_count"] <= result["pair_count"]
    for cluster in result["clusters"]:
        assert cluster["member_count"] == len(cluster["member_ids"])
        assert 0.0 <= (cluster["min_similarity"] or 0.0) <= 1.0
        assert 0.0 <= (cluster["max_similarity"] or 0.0) <= 1.0
        assert cluster["min_similarity"] is None or cluster["min_similarity"] <= cluster["max_similarity"]


def test_order_independent(seed_rows: list[dict]) -> None:
    """输入乱序不改变簇成员与主房源（主房源按字段排序，不按数组下标）。"""
    forward = build_clusters(seed_rows)
    backward = build_clusters(list(reversed(seed_rows)))
    forward_members = sorted(_ids(cluster) for cluster in forward["clusters"])
    backward_members = sorted(_ids(cluster) for cluster in backward["clusters"])
    assert forward_members == backward_members == [[701, 702], [703]]
    assert {cluster["primary_id"] for cluster in forward["clusters"]} == {
        cluster["primary_id"] for cluster in backward["clusters"]
    }
    assert forward["dedup_count"] == backward["dedup_count"] == 2


def test_deterministic_same_input(seed_rows: list[dict]) -> None:
    """同输入两次结果逐字相同（纯函数，无随机/无时间依赖）。"""
    first = json.dumps(build_clusters(seed_rows), sort_keys=True, ensure_ascii=False)
    second = json.dumps(build_clusters(seed_rows), sort_keys=True, ensure_ascii=False)
    assert first == second
