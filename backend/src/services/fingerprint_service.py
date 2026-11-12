"""算法 1：房源指纹去重（纯函数；DB 侧调用在 cluster_service）。

输入：已规范化的挂牌行（dict），至少含
  id / community / layout / area_sqm / floor / title / unit_price / list_date / completeness
输出：簇列表（成员、主房源、相似度摘要）+ 统计口径。
"""
from __future__ import annotations

from src.constants.limits import SIM_THRESHOLD
from src.utils.similarity import UnionFind, similarity_breakdown, title_tokens


def _primary_key(row: dict) -> tuple:
    """主房源排序键：挂牌最早 -> 字段最全 -> id 最小。"""
    return (
        row.get("list_date") or "9999-99-99",
        -(row.get("completeness") or 0.0),
        row.get("id") or 0,
    )


def build_clusters(rows: list[dict], threshold: float = SIM_THRESHOLD) -> dict:
    """在 blocking key 内两两比较、连边、并查集聚类。"""
    if not rows:
        # 返回结构与非空分支保持一致（早期版本缺 duplicate_clusters / member_total，
        # 空库时按 key 读取的调用方会 KeyError）
        return {
            "clusters": [],
            "edge_count": 0,
            "pair_count": 0,
            "duplicate_clusters": 0,
            "member_total": 0,
            "dedup_count": 0,
            "singletons": 0,
        }

    uf = UnionFind(len(rows))
    blocks: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        blocks.setdefault(f"{row['community']}::{row['layout']}", []).append(index)

    pair_count = 0
    edge_count = 0
    pair_scores: dict[tuple[int, int], float] = {}
    for indices in blocks.values():
        # 面积缺失的挂牌无法比较面积，不参与连边（独占一簇，均价口径里另算 unknown）
        indices = [i for i in indices if rows[i].get("area_sqm") is not None]
        for offset, left in enumerate(indices):
            for right in indices[offset + 1:]:
                pair_count += 1
                breakdown = similarity_breakdown(rows[left], rows[right])
                if breakdown["score"] >= threshold:
                    pair_scores[(left, right)] = breakdown["score"]
                    if uf.union(left, right):
                        edge_count += 1

    clusters: list[dict] = []
    for _, members in uf.groups().items():
        member_rows = [rows[i] for i in members]
        primary = min(member_rows, key=_primary_key)
        scores = [
            score
            for (left, right), score in pair_scores.items()
            if left in members and right in members
        ]
        platforms = {row.get("source_id") for row in member_rows}
        prices = [float(row.get("unit_price") or 0) for row in member_rows if row.get("unit_price")]
        clusters.append(
            {
                "member_ids": sorted(row["id"] for row in member_rows),
                "member_count": len(member_rows),
                "primary_id": primary["id"],
                "community": primary["community"],
                "layout": primary["layout"],
                "platform_count": len(platforms),
                "avg_unit_price": round(sum(prices) / len(prices)) if prices else None,
                "min_similarity": round(min(scores), 4) if scores else None,
                "max_similarity": round(max(scores), 4) if scores else None,
                "is_duplicate": len(member_rows) > 1,
                "area_sqm": primary.get("area_sqm"),
                "title_tokens": len(title_tokens(primary.get("title"))),
            }
        )

    clusters.sort(key=lambda item: (item["community"], item["layout"], item["primary_id"]))
    duplicates = [c for c in clusters if c["is_duplicate"]]
    return {
        "clusters": clusters,
        "edge_count": edge_count,
        "pair_count": pair_count,
        "duplicate_clusters": len(duplicates),
        "member_total": sum(c["member_count"] for c in clusters),
        "dedup_count": len(clusters),
        "singletons": sum(1 for c in clusters if not c["is_duplicate"]),
    }
