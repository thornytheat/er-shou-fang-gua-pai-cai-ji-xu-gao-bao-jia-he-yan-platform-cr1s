"""单元测试基座：只喂纯函数，不连 MySQL / Redis / HTTP。

被测模块（全部为纯函数，签名只吃 dict/list）：
  src/utils/similarity.py          规范化 + 加权相似 + 并查集
  src/services/fingerprint_service.py  算法 1 房源指纹去重
  src/services/price_service.py    算法 2 稳健 z 价格异常
  src/services/parsers.py          五平台字段解析与归一

测试输入取真实 seed 切片（fixtures/platforms.json 第 1 页第 1 条），
期望值全部手算，浮点断言一律走 pytest.approx。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

FIXTURE_ROOT = BACKEND_ROOT / "fixtures"

# 真实 seed 切片：云栖湾三居，同一套房在「链家式聚合站 / 中介朋友圈 / 业主论坛」的三条记录。
# 字段口径与 scripts/seed_demo.py 落库后一致（area 取整、floor 已归一、title 原文）。
SEED_ROWS: list[dict] = [
    {
        "id": 701,
        "source_id": 1,
        "community": "云栖湾",
        "layout": "三居",
        "area_sqm": 140,
        "floor": 3,
        "total_floors": 18,
        "title": "云栖湾 3室2厅 140㎡ 低楼层 精装 满五 近地铁",
        "unit_price": 44419,
        "list_date": "2026-10-14",
        "completeness": 1.0,
    },
    {
        "id": 702,
        "source_id": 4,
        "community": "云栖湾",
        "layout": "三居",
        "area_sqm": 140,
        "floor": 3,
        "total_floors": 18,
        "title": "云栖湾 3室2厅 140㎡ 低楼层 精装 满五 本周可谈",
        "unit_price": 45000,
        "list_date": "2026-10-12",
        "completeness": 0.875,
    },
    {
        "id": 703,
        "source_id": 3,
        "community": "云栖湾",
        "layout": "三居",
        "area_sqm": 90,
        "floor": 12,
        "total_floors": 18,
        "title": "云栖湾 3室2厅 90㎡ 高楼层 随时看房",
        "unit_price": 70000,
        "list_date": "2026-10-15",
        "completeness": 0.875,
    },
]


def _copy(rows: list[dict]) -> list[dict]:
    return [dict(row) for row in rows]


@pytest.fixture(scope="session")
def platform_payload() -> dict:
    return json.loads((FIXTURE_ROOT / "platforms.json").read_text(encoding="utf-8"))


@pytest.fixture()
def platform_items(platform_payload: dict) -> dict[str, dict]:
    """五个平台各自第 1 页第 1 条原始记录（kind -> item）。"""
    return {
        bucket["kind"]: dict(bucket["pages"][0]["items"][0])
        for bucket in platform_payload["platforms"].values()
    }


@pytest.fixture()
def seed_rows() -> list[dict]:
    return _copy(SEED_ROWS)


@pytest.fixture()
def row_a(seed_rows: list[dict]) -> dict:
    """链家式那条：字段最全（completeness 1.0），挂牌日 2026-10-14。"""
    return seed_rows[0]


@pytest.fixture()
def row_b(seed_rows: list[dict]) -> dict:
    """朋友圈那条：挂牌最早（2026-10-12），与 row_a 同一套房。"""
    return seed_rows[1]
