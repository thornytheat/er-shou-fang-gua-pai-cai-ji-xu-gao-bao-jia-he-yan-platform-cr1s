"""确定性 fixture 生成器（离线一次性运行，产物 sources.json / platforms.json）。

为什么用生成器而不是手写 240 条：主流程验收对若干数值有逐字要求
（兰亭苑三居 去重前 61,200 -> 去重后 58,900；阳光里两居 偏离 41.2%、z=4.31），
既要满足这些等式，又要保证去重算法恰好切出 32 簇 / 78 条重复，
手写无法自洽，因此用固定构造 + 断言生成。

运行：
    cd backend && PYTHONPATH=. python3 fixtures/generate_fixtures.py
生成后 fixture 就是只读快照，运行时不再执行本脚本。
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from src.services.fingerprint_service import build_clusters
from src.services.parsers import parse_item
from src.services.price_service import block_stats, classify, median

HERE = Path(__file__).resolve().parent
TODAY = "2026-11-12"

SOURCES = [
    (
        "lianjia_agg",
        "链家式聚合站",
        "aggregator",
        "https://hz.lianjia-like.example.com/ershoufang",
        "daily 08:30",
        60,
        10,
        "研究组主力源：字段最规整，单价/总价/精确楼层都有",
    ),
    (
        "anjuke_portal",
        "安居式信息港",
        "portal",
        "https://hz.anjuke-like.example.com/sale",
        "daily 08:40",
        45,
        10,
        "信息港：楼层只给「中楼层(共18层)」，需要补层号",
    ),
    (
        "owner_bbs",
        "业主论坛",
        "forum",
        "https://bbs.hz-owner.example.cn/forum-68",
        "daily 09:10",
        30,
        10,
        "业主直售口吻，日期是中文写法，没有联系方式字段",
    ),
    (
        "agent_moments",
        "中介朋友圈存档",
        "moments",
        "https://archive.hz-agent.example.com/moments/2026-11",
        "twice_daily 08:30/20:30",
        20,
        10,
        "门店朋友圈截图转录，标题带表情词，单价常有小幅上调",
    ),
    (
        "store_notice",
        "门店群公告",
        "notice",
        "https://notice.hz-store.example.com/rentlens",
        "hourly 08:00-21:00",
        90,
        10,
        "门店群公告，一行一条，日期只有 MM-DD",
    ),
]

# ---------------------------------------------------------------------------
# 8 个 小区×户型 分组（blocking key），共 194 个唯一房源 + 46 条重复挂牌
# ---------------------------------------------------------------------------
BLOCKS = [
    {
        "community": "兰亭苑",
        "layout": "三居",
        "count": 28,
        "extras": 14,
        "triples": 7,
        "base_area": 118,
        "total_floors": 18,
        # 验收口径：28 条唯一房源均价 58,900；7 套高价房各被 2 个平台重复挂牌，
        # 42 条合起来均价 61,200（重复挂牌把均值抬了 2,300 元/㎡）
        "dup_indices": [21, 22, 23, 24, 25, 26, 27],
        "dup_sum": 459_900,
        "other_sum": 1_189_300,
        "extra_sum": 921_200,
        "dup_base": [62_000, 63_000, 64_000, 65_000, 66_000, 67_000, 68_000],
        "other_base": [51_000, 51_800, 52_500, 53_200, 53_900, 54_600, 55_300,
                       56_000, 56_700, 57_400, 58_100, 58_800, 59_500, 60_200,
                       60_900, 61_600, 62_300, 55_000, 56_500, 58_000, 59_500],
        "flags": [],
    },
    {
        "community": "阳光里",
        "layout": "两居",
        "count": 26,
        "extras": 6,
        "triples": 2,
        "base_area": 78,
        "total_floors": 18,
        # 显式构造：中位 56,000、MAD 3,610、钓鱼价 79,072 -> 偏离 41.2%、z=4.31
        "prices": (
            [56_000 - d for d in [6_100, 5_500, 5_000, 4_600, 4_200, 3_900, 3_610,
                                  3_200, 2_800, 2_400, 2_000, 1_600, 1_200]]
            + [56_000 + d for d in [1_200, 1_600, 2_000, 2_400, 2_800, 3_200, 3_610,
                                    3_900, 4_200, 4_600, 5_000, 5_500]]
            + [79_072]
        ),
        "flags": [(25, "high")],
    },
    {
        "community": "兰亭苑",
        "layout": "两居",
        "count": 24,
        "extras": 5,
        "triples": 1,
        "base_area": 86,
        "total_floors": 18,
        "base_price": 52_000,
        "flags": [(6, "uncertain")],
    },
    {
        "community": "阳光里",
        "layout": "三居",
        "count": 22,
        "extras": 5,
        "triples": 1,
        "base_area": 116,
        "total_floors": 18,
        "base_price": 62_400,
        "flags": [(4, "high"), (15, "high")],
    },
    {
        "community": "云栖湾",
        "layout": "三居",
        "count": 26,
        "extras": 5,
        "triples": 1,
        "base_area": 120,
        "total_floors": 18,
        "base_price": 66_800,
        "flags": [(8, "high"), (20, "low")],
    },
    {
        "community": "云栖湾",
        "layout": "两居",
        "count": 24,
        "extras": 5,
        "triples": 1,
        "base_area": 88,
        "total_floors": 18,
        "base_price": 54_600,
        "flags": [(10, "high"), (2, "low")],
    },
    {
        "community": "静安里",
        "layout": "两居",
        "count": 24,
        "extras": 3,
        "triples": 0,
        "base_area": 76,
        "total_floors": 18,
        "base_price": 46_200,
        "flags": [(7, "high"), (19, "high")],
        "missing_area": [12, 21],
    },
    {
        "community": "静安里",
        "layout": "一居",
        "count": 20,
        "extras": 3,
        "triples": 1,
        "base_area": 46,
        "total_floors": 26,
        "base_price": 38_400,
        "flags": [(9, "low"), (16, "uncertain")],
        "missing_area": [1],
    },
]

BANDS = ["中楼层", "高楼层", "低楼层", "中楼层", "高楼层", "低楼层"]
# 同一小区×户型内 1.5%~9% 的正常价差（装修/朝向/楼层/税费），保证 MAD 是真实的离散度
OFFSET_PCT = [0, 3.2, -3.6, 6.1, -5.4, 1.5, -1.2, 4.3, -6.9, 2.6, -2.1, 8.4,
              -0.6, 3.5, -7.3, 5.2, -4.7, 1.8, -1.5, 7.0, 2.8, -2.5, 6.0, -5.6]
FLAG_MULTIPLIER = {"high": [1.34, 1.39, 1.33, 1.41, 1.35], "low": [0.66, 0.65, 0.67], "uncertain": [1.27, 1.26]}
SOURCE_KEYS = [spec[0] for spec in SOURCES]
SOURCE_KINDS = {spec[0]: spec[2] for spec in SOURCES}
HOSTS = {
    "lianjia_agg": ["王莉", "陈默", "赵珂"],
    "anjuke_portal": ["周洋", "李萌", "孙骁"],
    "owner_bbs": ["业主·老徐", "业主·阿岚", "业主·小满"],
    "agent_moments": ["经纪人·许诺", "经纪人·韩梅", "经纪人·关鹏"],
    "store_notice": ["店长·刘楠", "店长·吴越", "店长·毕谦"],
}
PHONES = ["138 0013 8000", "139 1122 3344", "137 5566 7788", "186 2211 9090", "135 8899 0011"]


def adjust_sum(values: list[int], target: int) -> list[int]:
    """整体平移 + 余数分配到前几个元素，保证总和精确等于 target（形状不变）。"""
    diff = target - sum(values)
    step = diff // len(values)
    values = [value + step for value in values]
    remainder = target - sum(values)
    index = 0
    while remainder != 0:
        delta = 1 if remainder > 0 else -1
        values[index % len(values)] += delta
        remainder -= delta
        index += 1
    return values


def build_block_prices(block: dict) -> list[int]:
    if "prices" in block:
        return list(block["prices"])
    if "dup_sum" in block:
        dup = adjust_sum(list(block["dup_base"]), block["dup_sum"])
        other = adjust_sum(list(block["other_base"]), block["other_sum"])
        return other + dup
    base = block["base_price"]
    prices = [
        int(round(base * (1 + OFFSET_PCT[index % len(OFFSET_PCT)] / 100)))
        for index in range(block["count"])
    ]
    counters = {"high": 0, "low": 0, "uncertain": 0}
    core_median = median([float(value) for value in prices]) or float(base)
    for index, kind in block["flags"]:
        multipliers = FLAG_MULTIPLIER[kind]
        multiplier = multipliers[counters[kind] % len(multipliers)]
        counters[kind] += 1
        prices[index] = int(round(core_median * multiplier))
    return prices


def duplicate_indices(block: dict, prices: list[int], flag_indices: set[int], missing: set[int]) -> list[int]:
    """选出被重复挂牌的房源下标：兰亭苑三居固定取价格最高的一批（痛点来源）。"""
    if "dup_indices" in block:
        return list(block["dup_indices"])
    candidates = [i for i in range(len(prices)) if i not in flag_indices and i not in missing]
    step = max(1, len(candidates) // max(1, block["extras"]))
    picked: list[int] = []
    cursor = 0
    while len(picked) < block["extras"] and cursor < len(candidates):
        picked.append(candidates[cursor])
        cursor += step
    while len(picked) < block["extras"]:
        picked.append(candidates[len(picked)])
    return picked[: block["extras"]]


def title_for(kind: str, community: str, layout: str, area: int, band: str, total: float) -> str:
    rooms = {"三居": "3室2厅", "两居": "2室2厅", "一居": "1室1厅"}[layout]
    tail = {
        "aggregator": "满五 近地铁",
        "portal": "满五唯一 近地铁",
        "forum": "业主自荐 满五",
        "moments": "满五 本周可谈",
        "notice": "满五 随时看房",
    }[kind]
    unit = "㎡" if kind in {"aggregator", "moments", "notice"} else "平"
    return f"{community} {rooms} {area}{unit} {band} 精装 {tail}"


def main() -> None:
    primaries: list[dict] = []
    extra_rows: list[dict] = []
    cluster_plan: list[tuple[int, int]] = []  # (primary_index_global, extra_count)

    for block in BLOCKS:
        prices = build_block_prices(block)
        missing = set(block.get("missing_area", []))
        flag_indices = {index for index, _ in block["flags"]}
        dup_indices = duplicate_indices(block, prices, flag_indices, missing)
        extras_per_dup = [0] * len(dup_indices)
        triples = block["triples"]
        for position in range(block["extras"]):
            extras_per_dup[position % len(dup_indices)] += 1
        # triples 决定「有几簇是 2 条重复」，其余按 1 条轮转，保证簇数 = extras - triples
        for position in range(block["extras"]):
            if extras_per_dup[position % len(dup_indices)] > 1:
                continue

        start = len(primaries)
        for index, price in enumerate(prices):
            band = BANDS[index % len(BANDS)]
            primaries.append(
                {
                    "community": block["community"],
                    "layout": block["layout"],
                    "area_sqm": None if index in missing else block["base_area"] + index,
                    "floor_band": band,
                    "total_floors": block["total_floors"],
                    "unit_price": None if index in missing else price,
                    "total_price_wan": None if index in missing else round(price * (block["base_area"] + index) / 10000, 2),
                    "list_date": None,
                    "block_index": index,
                    "flag_band": block["layout"],
                    "missing_area": index in missing,
                }
            )

        # 簇的成员数：triples 个簇 3 条（主 + 2 条重复），其余簇 2 条
        cluster_sizes = [3] * triples + [2] * (block["extras"] - triples * 2)
        assert len(cluster_sizes) == block["extras"] - triples, (block["community"], block["layout"])
        cursor = 0
        for size in cluster_sizes:
            primary_index = dup_indices[cursor % len(dup_indices)]
            cursor += 1
            global_index = start + primary_index
            cluster_plan.append((global_index, size - 1))

    # ---- 挂牌日：主房源在前，重复挂牌晚 1~5 天（都不晚于 2026-11-10） ----
    anchor = date(2026, 10, 14)
    for order, row in enumerate(primaries):
        offset = (order * 9) % 24
        row["_primary_date"] = (anchor + timedelta(days=offset)).isoformat()

    # ---- 重复挂牌 ----
    cluster_members: list[dict] = []
    for number, (global_index, extra_count) in enumerate(cluster_plan):
        primary = primaries[global_index]
        base_day = date.fromisoformat(primary["_primary_date"])
        for extra_offset in range(extra_count):
            delta = [0, 200, 300, 100, 200][extra_offset % 5]
            price = primary["unit_price"] + delta if primary["unit_price"] else None
            cluster_members.append(
                {
                    "community": primary["community"],
                    "layout": primary["layout"],
                    "area_sqm": primary["area_sqm"],
                    "floor_band": primary["floor_band"],
                    "total_floors": primary["total_floors"],
                    "unit_price": price,
                    "total_price_wan": round(price * primary["area_sqm"] / 10000, 2) if price and primary["area_sqm"] else None,
                    "_primary_date": min(
                        date(2026, 11, 10), base_day + timedelta(days=1 + extra_offset)
                    ).isoformat(),
                    "_extra_offset": extra_offset,
                    "cluster_of": global_index,
                    "missing_area": primary["missing_area"],
                }
            )

    rows = primaries + cluster_members
    rows.sort(key=lambda row: (row["_primary_date"], row["community"], row["layout"], row.get("cluster_of", -1)))

    # ---- 平台分派：主房源轮转，重复挂牌优先分给该房源还没出现过的平台 ----
    loads = {key: 0 for key in SOURCE_KEYS}
    for index, row in enumerate(primaries):
        key = SOURCE_KEYS[index % len(SOURCE_KEYS)]
        row["source_key"] = key
        loads[key] += 1
    for row in cluster_members:
        primary_source = primaries[row["cluster_of"]]["source_key"]
        used = {primary_source}
        for other in cluster_members:
            if other is not row and other["cluster_of"] == row["cluster_of"]:
                if other.get("source_key"):
                    used.add(other["source_key"])
        candidates = [key for key in SOURCE_KEYS if key not in used] or [key for key in SOURCE_KEYS if key != primary_source]
        key = min(candidates, key=lambda candidate: (loads[candidate], SOURCE_KEYS.index(candidate)))
        row["source_key"] = key
        loads[key] += 1

    assert all(count == 48 for count in loads.values()), loads

    # ---- 平台字段快照 ----
    counters = {key: 0 for key in SOURCE_KEYS}
    platforms: dict[str, dict] = {
        key: {"name": spec[1], "kind": spec[2], "page_size": spec[6], "throttle_pages": [], "pages": []}
        for key, spec in zip(SOURCE_KEYS, SOURCES)
    }
    ordered = sorted(rows, key=lambda row: (row["source_key"], row["_primary_date"], row.get("cluster_of", -1)))
    per_source: dict[str, list[dict]] = {key: [] for key in SOURCE_KEYS}
    for row in ordered:
        key = row["source_key"]
        counters[key] += 1
        band = row["floor_band"]
        total_floors = row["total_floors"]
        floor_no = {"低楼层": round(total_floors * 0.18), "中楼层": round(total_floors * 0.5), "高楼层": round(total_floors * 0.82)}[band]
        date_text = row["_primary_date"]
        if key == "anjuke_portal":
            date_text = date_text.replace("-", "/")
        elif key == "owner_bbs":
            date_text = date_text.replace("-", "年", 1).replace("-", "月", 1) + "日 21:14"
        elif key == "agent_moments":
            date_text = f"{date_text} 20:{10 + counters[key] % 40:02d}"
        elif key == "store_notice":
            date_text = date_text[5:]
        common = {
            "area": row["area_sqm"],
            "band": band,
            "total_floors": total_floors,
            "unit": row["unit_price"],
            "total": row["total_price_wan"],
        }
        host = HOSTS[key][counters[key] % len(HOSTS[key])]
        phone = PHONES[counters[key] % len(PHONES)]
        if key == "lianjia_agg":
            item = {
                "house_code": f"LJ-{100200 + counters[key]}",
                "resblock": row["community"] + ("小区" if counters[key] % 7 == 0 else ""),
                "huxing": {"三居": "3室2厅", "两居": "2室2厅", "一居": "1室1厅"}[row["layout"]],
                "build_area": f"{row['area_sqm']}.0" if row["area_sqm"] else "暂无",
                "floor_no": floor_no,
                "total_floors": total_floors,
                "unit_price_yuan": row["unit_price"],
                "total_price_wan": row["total_price_wan"],
                "online_date": date_text,
                "title": title_for("aggregator", row["community"], row["layout"], row["area_sqm"] or 0, band, row["total_price_wan"] or 0) if row["area_sqm"] else f"{row['community']} 户型待确认 总价{row['total_price_wan']}万",
                "agent": host,
                "phone": phone,
            }
        elif key == "anjuke_portal":
            item = {
                "info_id": f"AJ{800300 + counters[key]}",
                "community": row["community"] + ("家园" if counters[key] % 6 == 0 else ""),
                "huxing": f"{row['layout']}(按套内计)",
                "area": row["area_sqm"],
                "floor": f"{floor_no}/{total_floors}",
                "price_per_sqm": row["unit_price"],
                "total_price_wan": row["total_price_wan"],
                "pub_date": date_text,
                "subject": title_for("portal", row["community"], row["layout"], row["area_sqm"] or 0, f"{band}(共{total_floors}层)", row["total_price_wan"] or 0) if row["area_sqm"] else f"{row['community']} 待勘面积 总价{row['total_price_wan']}万",
                "broker": host,
                "tel": phone,
            }
        elif key == "owner_bbs":
            item = {
                "thread_id": f"BBS-{700400 + counters[key]}",
                "xiaoqu": row["community"] + ("一期" if counters[key] % 9 == 0 else ""),
                "huxing": row["layout"],
                "mianji": row["area_sqm"],
                "louceng": band,
                "zongceng": total_floors,
                "danjia": row["unit_price"],
                "total_price_wan": row["total_price_wan"],
                "post_date": date_text,
                "subject": title_for("forum", row["community"], row["layout"], row["area_sqm"] or 0, band, row["total_price_wan"] or 0) if row["area_sqm"] else f"自家{row['community']}房子 面积忘了 总价{row['total_price_wan']}万",
                "poster": host,
            }
        elif key == "agent_moments":
            item = {
                "archive_id": f"MM-{910500 + counters[key]}",
                "community": row["community"],
                "layout": row["layout"],
                "area_sqm": row["area_sqm"],
                "floor_no": floor_no,
                "total_floors": total_floors,
                "unit_price": row["unit_price"],
                "total_price_wan": row["total_price_wan"],
                "captured_at": date_text,
                "caption": title_for("moments", row["community"], row["layout"], row["area_sqm"] or 0, band, row["total_price_wan"] or 0) if row["area_sqm"] else f"{row['community']} 面积待补 总价{row['total_price_wan']}万",
                "agent": host,
                "phone": phone,
            }
        else:
            item = {
                "notice_id": f"GR-{620600 + counters[key]}",
                "xiaoqu": row["community"],
                "huxing": {"三居": "三居", "两居": "两居", "一居": "一居"}[row["layout"]],
                "mianji": row["area_sqm"],
                "louceng_desc": band,
                "zongceng": total_floors,
                "danjia": row["unit_price"],
                "total_price_wan": row["total_price_wan"],
                "riqi": date_text,
                "text": title_for("notice", row["community"], row["layout"], row["area_sqm"] or 0, band, row["total_price_wan"] or 0) if row["area_sqm"] else f"{row['community']}/面积待补/总价{row['total_price_wan']}万",
                "dianzhang": host,
            }
        per_source[key].append(item)
        row["_platform"] = key
        row["_item"] = item

    # ---- 401/429 限流：两个平台各有一页首次命中 429 ----
    throttle_plan = {"anjuke_portal": [3], "agent_moments": [2]}
    listing_count = 0
    for key, spec in zip(SOURCE_KEYS, SOURCES):
        bucket = platforms[key]
        page_size = spec[6]
        items = per_source[key]
        pages = [items[index:index + page_size] for index in range(0, len(items), page_size)]
        bucket["throttle_pages"] = throttle_plan.get(key, [])
        for offset, page_items in enumerate(pages):
            bucket["pages"].append({"page": offset + 1, "status": 200, "items": page_items})
            listing_count += len(page_items)

    # ---- 校验：解析 -> 去重 -> 均价 -> 价格标记 ----
    parsed: list[dict] = []
    for row in rows:
        parsed.append(parse_item(SOURCE_KINDS[row["_platform"]], row["_item"]))
    for index, row in enumerate(parsed):
        row["id"] = index + 1
        row["source_id"] = SOURCE_KEYS.index(rows[index]["source_key"]) + 1

    result = build_clusters(parsed)
    duplicates = [cluster for cluster in result["clusters"] if cluster["is_duplicate"]]
    print(f"listings={len(parsed)} unique={result['dedup_count']} clusters={len(duplicates)} "
          f"members={sum(cluster['member_count'] for cluster in duplicates)} edges={result['edge_count']}")
    assert len(parsed) == 240, len(parsed)
    assert result["dedup_count"] == 194, result["dedup_count"]
    assert len(duplicates) == 32, len(duplicates)
    assert sum(cluster["member_count"] for cluster in duplicates) == 78

    by_id = {row["id"]: row for row in parsed}
    for community, layout in [("兰亭苑", "三居"), ("阳光里", "两居")]:
        all_rows = [r for r in parsed if r["community"] == community and r["layout"] == layout]
        prim = [by_id[cluster["primary_id"]] for cluster in result["clusters"]
                if cluster["community"] == community and cluster["layout"] == layout]
        naive = sum(r["unit_price"] for r in all_rows if r["unit_price"]) / len([r for r in all_rows if r["unit_price"]])
        dedup = sum(r["unit_price"] for r in prim if r["unit_price"]) / len([r for r in prim if r["unit_price"]])
        print(f"  {community} {layout}: all={len(all_rows)} primary={len(prim)} naive_mean={naive:.2f} dedup_mean={dedup:.2f}")
        if (community, layout) == ("兰亭苑", "三居"):
            assert round(naive, 2) == 61200.00, naive
            assert round(dedup, 2) == 58900.00, dedup

    # 价格标记只做在「去重后的主房源」上：重复挂牌不参与分组分布
    from collections import defaultdict

    groups: dict[tuple, list] = defaultdict(list)
    for cluster in result["clusters"]:
        groups[(cluster["community"], cluster["layout"])].append(cluster)

    flag_counts = {"high": 0, "low": 0, "uncertain": 0}
    block_report = []
    for (community, layout), clusters in groups.items():
        primary_rows = [by_id[cluster["primary_id"]] for cluster in clusters]
        values = [float(row["unit_price"]) for row in primary_rows if row["area_sqm"] and row["unit_price"]]
        stats = block_stats(values)
        block_report.append((community, layout, stats))
        for row in primary_rows:
            verdict = classify(
                row["unit_price"],
                median_price=stats["median_price"],
                spread=stats["mad"],
                sample_size=stats["sample_size"],
                completeness=row["completeness"],
            )
            if verdict["flag_type"]:
                flag_counts[verdict["flag_type"]] += 1
                if (community, layout) == ("阳光里", "两居"):
                    assert verdict["flag_type"] == "high"
                    assert verdict["deviation_pct"] == 41.2, verdict
                    assert round(verdict["z_score"], 2) == 4.31, verdict
                print(f"  flag {verdict['flag_type']:9s} {community} {layout} unit={row['unit_price']} "
                      f"med={stats['median_price']} n={stats['sample_size']} mad={stats['mad']} "
                      f"dev={verdict['deviation_pct']}% z={verdict['z_score']} conf={verdict['confidence']}")
    for community, layout, stats in block_report:
        print(f"  block {community} {layout}: n={stats['sample_size']} med={stats['median_price']} "
              f"mad={stats['mad']} mean={stats['mean_price']} spread={stats['spread_pct']}%")
    print("  flag_counts:", flag_counts)
    assert flag_counts == {"high": 7, "low": 3, "uncertain": 2}, flag_counts

    sources_payload = [
        {
            "code": key,
            "name": name,
            "platform": kind,
            "base_url": url,
            "frequency": freq,
            "rate_limit_per_min": rate,
            "page_size": page_size,
            "note": note,
        }
        for key, name, kind, url, freq, rate, page_size, note in SOURCES
    ]
    (HERE / "sources.json").write_text(json.dumps(sources_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (HERE / "platforms.json").write_text(
        json.dumps(
            {
                "generated_by": "fixtures/generate_fixtures.py",
                "generated_for": "rentlens batch-20261112b gb-577",
                "listing_count": listing_count,
                "platforms": platforms,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"fixtures written: {listing_count} listings across {len(platforms)} platforms")


if __name__ == "__main__":
    main()
