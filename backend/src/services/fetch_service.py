"""采集层：读平台 fixture → 处理分页与 429 退避 → 交给解析器。

真实抓取时这一层是 HTTP 客户端；演示环境用 fixtures/platforms.json
里的确定性快照，但分页、限流（429）、指数退避、逐页解析的行为与真机一致：
  · 每个平台按 page_size 分页抓取
  · throttle_pages 指定的页第一次命中 429，按 base * 2^n 退避后重试
  · 每次运行记录 pages / items / throttled / backoff_ms，写进运行记录
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from src.config.settings import settings
from src.constants.limits import DEFAULT_BACKOFF_BASE_MS, MAX_THROTTLE_RETRIES
from src.services.parsers import parse_item
from src.utils.logger import get_logger

logger = get_logger("fetch")


def fixture_root() -> Path:
    root = Path(settings.fixture_dir)
    if not root.is_absolute():
        root = Path(__file__).resolve().parents[2] / settings.fixture_dir
    return root


def load_sources() -> list[dict]:
    return json.loads((fixture_root() / "sources.json").read_text(encoding="utf-8"))


def load_platforms() -> dict:
    return json.loads((fixture_root() / "platforms.json").read_text(encoding="utf-8"))


def _sleep_backoff(attempt: int, base_ms: int) -> int:
    delay = base_ms * (2 ** attempt)
    # 上限 4 秒，避免演示环境的退避把接口拖死
    delay = min(delay, 4000)
    time.sleep(delay / 1000.0)
    return delay


def crawl_source(source: dict, platforms: dict, simulate_throttle: bool = True) -> dict:
    """抓取单个平台：返回解析后的挂牌行 + 本次运行的采集统计。

    simulate_throttle=False 时（seed 首次灌数）不睡退避，直接按快照解析。
    """
    bucket = platforms["platforms"].get(source["code"])
    if bucket is None:
        raise FileNotFoundError(f"missing fixture for source {source['code']}")

    base_ms = int(settings.crawl_backoff_base_ms or DEFAULT_BACKOFF_BASE_MS)
    throttle_pages = set(bucket.get("throttle_pages") or []) if simulate_throttle else set()
    throttled = 0
    backoff_ms = 0
    pages_fetched = 0
    rows: list[dict] = []
    throttle_log: list[dict] = []

    for page in bucket["pages"]:
        attempts = 0
        page_number = int(page["page"])
        while True:
            if page_number in throttle_pages and attempts == 0:
                throttled += 1
                delay = _sleep_backoff(attempts, base_ms)
                backoff_ms += delay
                throttle_log.append({"page": page_number, "status": 429, "wait_ms": delay})
                attempts += 1
                if attempts > MAX_THROTTLE_RETRIES:
                    break
                continue
            break
        pages_fetched += 1
        for item in page["items"]:
            parsed = parse_item(bucket["kind"], item)
            parsed["source_code"] = source["code"]
            parsed["raw_json"] = json.dumps(item, ensure_ascii=False)
            rows.append(parsed)

    logger.info(
        "[fetch] %s pages=%s items=%s throttled=%s backoff_ms=%s",
        source["code"], pages_fetched, len(rows), throttled, backoff_ms,
    )
    return {
        "pages_fetched": pages_fetched,
        "items_fetched": len(rows),
        "throttled": throttled,
        "backoff_ms": backoff_ms,
        "throttle_log": throttle_log,
        "rows": rows,
    }
