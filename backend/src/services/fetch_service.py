"""采集层：读平台 fixture → 处理分页与 429 退避 → 交给解析器。

真实抓取时这一层是 HTTP 客户端；演示环境用 fixtures/platforms.json
里的确定性快照，但分页、限流（429）、指数退避、逐页解析的行为与真机一致：
  · 每个平台按 page_size 分页抓取
  · throttle_pages 指定的页第一次命中 429，按 base * 2^n 退避后重试
  · 每次运行记录 pages / items / throttled / backoff_ms，写进运行记录
  · 任何一页没取全（异常 / 429 重试耗尽）都显式抛 FetchIncomplete，
    由 ingest 层把整个来源隔离，绝不返回截断后的半批数据
  · FAULT_INJECTION 环境变量可模拟 crash / partial_page / empty 三类故障
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from src.config.settings import settings
from src.constants.enums import FaultKind, QuarantineReason
from src.constants.limits import DEFAULT_BACKOFF_BASE_MS, MAX_THROTTLE_RETRIES
from src.services.parsers import parse_item
from src.utils.logger import get_logger

logger = get_logger("fetch")


class FetchIncomplete(RuntimeError):
    """来源取数不完整：携带隔离原因与已取页统计，供整源隔离落批。"""

    def __init__(
        self,
        source_code: str,
        reason: str,
        pages_expected: int,
        pages_fetched: int,
        detail: str = "",
        items_fetched: int = 0,
    ):
        super().__init__(f"source {source_code} fetch incomplete: {reason} ({detail})")
        self.source_code = source_code
        self.reason = reason
        self.pages_expected = pages_expected
        self.pages_fetched = pages_fetched
        self.items_fetched = items_fetched
        self.detail = detail


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


def _fault_plan() -> dict[str, str]:
    """解析 FAULT_INJECTION："source:kind,source:kind" → {source: kind}。"""
    plan: dict[str, str] = {}
    for chunk in (settings.fault_injection or "").split(","):
        chunk = chunk.strip()
        if not chunk or ":" not in chunk:
            continue
        code, kind = chunk.split(":", 1)
        if kind in {item.value for item in FaultKind if item is not FaultKind.OFF}:
            plan[code.strip()] = kind.strip()
    return plan


def crawl_source(source: dict, platforms: dict, simulate_throttle: bool = True) -> dict:
    """抓取单个平台：返回解析后的挂牌行 + 本次运行的采集统计。

    simulate_throttle=False 时（seed 首次灌数）不睡退避，直接按快照解析。
    取数不完整时抛 FetchIncomplete（含原因），调用方必须整源隔离。
    """
    code = source["code"]
    bucket = platforms["platforms"].get(code)
    if bucket is None:
        raise FileNotFoundError(f"missing fixture for source {code}")

    base_ms = int(settings.crawl_backoff_base_ms or DEFAULT_BACKOFF_BASE_MS)
    throttle_pages = set(bucket.get("throttle_pages") or []) if simulate_throttle else set()
    fault = _fault_plan().get(code, FaultKind.OFF.value) if simulate_throttle else FaultKind.OFF.value
    expected_pages = len(bucket["pages"])
    throttled = 0
    backoff_ms = 0
    pages_fetched = 0
    rows: list[dict] = []
    throttle_log: list[dict] = []

    # 故障注入 1：整源崩溃（连接失败 / 5xx），一页都拿不到
    if fault == FaultKind.CRASH.value:
        raise FetchIncomplete(
            code, QuarantineReason.FETCH_CRASH.value, expected_pages, 0,
            detail="注入故障：平台连接被拒绝（crash）",
        )

    for index, page in enumerate(bucket["pages"]):
        page_number = int(page["page"])
        attempts = 0
        while True:
            if page_number in throttle_pages and attempts == 0:
                throttled += 1
                delay = _sleep_backoff(attempts, base_ms)
                backoff_ms += delay
                throttle_log.append({"page": page_number, "status": 429, "wait_ms": delay})
                attempts += 1
                if attempts > MAX_THROTTLE_RETRIES:
                    # 429 重试耗尽：这一页没取到，半批数据绝不能当成功返回
                    raise FetchIncomplete(
                        code, QuarantineReason.PAGE_INCOMPLETE.value,
                        expected_pages, pages_fetched,
                        detail=f"第 {page_number} 页 429 重试 {MAX_THROTTLE_RETRIES} 次仍失败",
                        items_fetched=len(rows),
                    )
                continue
            break

        # 故障注入 2：中途某页失败（分页没取全），前面几页的数据必须丢弃
        if fault == FaultKind.PARTIAL_PAGE.value and index == max(1, expected_pages // 2):
            raise FetchIncomplete(
                code, QuarantineReason.PAGE_INCOMPLETE.value,
                expected_pages, pages_fetched,
                detail=f"注入故障：第 {page_number} 页网关超时（partial_page）",
                items_fetched=len(rows),
            )

        try:
            for item in page["items"]:
                parsed = parse_item(bucket["kind"], item)
                parsed["source_code"] = code
                parsed["raw_json"] = json.dumps(item, ensure_ascii=False)
                rows.append(parsed)
        except Exception as exc:  # noqa: BLE001 - 解析失败同样按取数不完整处理
            raise FetchIncomplete(
                code, QuarantineReason.PARSE_ERROR.value,
                expected_pages, pages_fetched,
                detail=f"第 {page_number} 页解析失败：{exc}",
                items_fetched=len(rows),
            ) from exc
        pages_fetched += 1

    if pages_fetched != expected_pages:
        raise FetchIncomplete(
            code, QuarantineReason.PAGE_INCOMPLETE.value,
            expected_pages, pages_fetched,
            detail=f"期望 {expected_pages} 页实际 {pages_fetched} 页",
        )

    # 故障注入 3：页面都 200 但解析 0 条（疑似被重定向到空列表页）
    if fault == FaultKind.EMPTY.value or not rows:
        raise FetchIncomplete(
            code, QuarantineReason.EMPTY_SNAPSHOT.value,
            expected_pages, pages_fetched,
            detail="注入故障：全部页面 200 但解析 0 条（empty）" if fault == FaultKind.EMPTY.value
            else "全部页面 200 但解析 0 条，疑似空快照",
        )

    logger.info(
        "[fetch] %s pages=%s items=%s throttled=%s backoff_ms=%s",
        code, pages_fetched, len(rows), throttled, backoff_ms,
    )
    return {
        "pages_expected": expected_pages,
        "pages_fetched": pages_fetched,
        "items_fetched": len(rows),
        "throttled": throttled,
        "backoff_ms": backoff_ms,
        "throttle_log": throttle_log,
        "rows": rows,
    }
