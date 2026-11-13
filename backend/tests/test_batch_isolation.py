"""按来源完整落批的集成测试（SQLite 内存库，不依赖 MySQL/Redis）。

覆盖需求四件事：
  1. 来源取数不完整 → 整源隔离：不改写该源挂牌，且不影响均价/工单/导出
  2. 完整来源按本次快照原子替换；同一批重复运行只生效一次（unchanged，不重算）
  3. 采集运行逐源记录 收到 / 隔离 / 替换 条数及原因
  4. 人工复核与改价在再次采集后仍对应原房（自然键稳定 → 行 id 不漂移）
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.config import settings as settings_module
from src.constants.enums import IngestStatus, SourceBatchStatus
from src.models import Base
from src.models.cluster import ListingCluster
from src.models.listing import Listing
from src.models.price_flag import PriceFlag
from src.models.source import Source
from src.models.source_batch import SourceBatch
from src.services import cluster_service, export_service, fetch_service, ingest_service

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)()
    platforms = json.loads((FIXTURE_ROOT / "platforms.json").read_text(encoding="utf-8"))
    sources_json = json.loads((FIXTURE_ROOT / "sources.json").read_text(encoding="utf-8"))
    for index, spec in enumerate(sources_json):
        session.add(
            Source(
                code=spec["code"], name=spec["name"], platform=spec["platform"],
                base_url=spec["base_url"], frequency=spec["frequency"],
                rate_limit_per_min=spec["rate_limit_per_min"], page_size=spec["page_size"],
                note=spec.get("note"), sort_order=index, enabled=True,
            )
        )
    session.flush()
    yield session, platforms
    session.close()
    engine.dispose()


@pytest.fixture(autouse=True)
def _isolate_fixture_loader(monkeypatch):
    """每个用例独立持有一份 platforms 副本，内存篡改不串用例、不碰磁盘 fixture。"""
    payload = json.loads((FIXTURE_ROOT / "platforms.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(fetch_service, "load_platforms", lambda: payload)
    monkeypatch.setattr(
        "src.services.ingest_service.fetch_service.load_platforms", lambda: payload
    )
    return payload


def _seed_full_snapshot(session, platforms) -> None:
    """模拟 seed：按 fixture 完整灌一批挂牌并完成首次重算。"""
    sources = session.scalars(select(Source).order_by(Source.id)).all()
    for source in sources:
        outcome = fetch_service.crawl_source(
            {"code": source.code, "name": source.name}, platforms, simulate_throttle=False
        )
        for row in outcome["rows"]:
            from datetime import date

            session.add(
                Listing(
                    source_id=source.id,
                    source_listing_no=row["source_listing_no"],
                    community=row["community"],
                    layout=row["layout"],
                    area_sqm=row.get("area_sqm"),
                    floor=row.get("floor"),
                    total_floors=row.get("total_floors"),
                    floor_band=row.get("floor_band"),
                    unit_price=row.get("unit_price"),
                    total_price_wan=row.get("total_price_wan"),
                    list_date=date.fromisoformat(row["list_date"]) if row.get("list_date") else None,
                    title=row.get("title") or "",
                    agent_name=row.get("agent_name"),
                    agent_contact=row.get("agent_contact"),
                    completeness=row.get("completeness") or 0.0,
                    raw=row.get("raw_json"),
                    quarantined=False,
                )
            )
        session.add(
            SourceBatch(
                run_id=0, source_id=source.id, source_code=source.code,
                status=SourceBatchStatus.REPLACED.value,
                pages_expected=outcome["pages_fetched"], pages_fetched=outcome["pages_fetched"],
                received_count=len(outcome["rows"]), replaced_count=len(outcome["rows"]),
                content_hash=ingest_service._content_hash(outcome["rows"]),
            )
        )
    session.flush()
    cluster_service.recompute(session)
    session.flush()


def _set_fault(monkeypatch, plan: str) -> None:
    monkeypatch.setattr(settings_module.settings, "fault_injection", plan)


def test_full_run_atomically_replaces_and_writes_batches(db, monkeypatch) -> None:
    session, platforms = db
    _set_fault(monkeypatch, "")
    _seed_full_snapshot(session, platforms)
    listing_before = session.scalar(select(func.count()).select_from(Listing))
    assert listing_before == 240

    run = ingest_service.run_ingest(session, operator_email="analyst@rentlens.io")
    assert run.status == IngestStatus.SUCCESS.value
    # 同一批快照：5 个源全部 unchanged，不产生任何新增/更新/删除，也不触发重算
    assert run.created_count == 0 and run.updated_count == 0
    assert run.summary["recomputed"] is False
    batches = ingest_service.list_batches_by_run(session, run.id)
    assert len(batches) == 5
    assert all(batch["status"] == SourceBatchStatus.UNCHANGED.value for batch in batches)
    assert session.scalar(select(func.count()).select_from(Listing)) == 240


def test_crash_isolates_whole_source_without_touching_its_listings(db, monkeypatch) -> None:
    session, platforms = db
    _set_fault(monkeypatch, "")
    _seed_full_snapshot(session, platforms)
    target = session.scalar(select(Source).where(Source.code == "anjuke_portal"))
    other = session.scalar(select(Source).where(Source.code == "lianjia_agg"))
    target_rows_before = session.scalars(
        select(Listing).where(Listing.source_id == target.id)
    ).all()
    target_snapshot = {(r.source_listing_no, r.unit_price, r.title) for r in target_rows_before}
    flags_before = session.scalar(select(func.count()).select_from(PriceFlag))

    # 安居源整源崩溃
    _set_fault(monkeypatch, "anjuke_portal:crash")
    run = ingest_service.run_ingest(session, source_ids=[target.id], operator_email="a@b.io")

    assert run.status == IngestStatus.FAILED.value
    # 隔离不允许改写工单：工单行总数与隔离前一致（只是该源的工单从队列口径隐藏）
    assert session.scalar(select(func.count()).select_from(PriceFlag)) == flags_before
    batch = ingest_service.list_batches_by_run(session, run.id)[0]
    assert batch["status"] == SourceBatchStatus.ISOLATED.value
    assert batch["reason"] == "fetch_crash"
    assert batch["received_count"] == 0
    assert batch["isolated_count"] == 48

    # 该源挂牌一条没被改写，但全部进入隔离态
    target_rows_after = session.scalars(
        select(Listing).where(Listing.source_id == target.id)
    ).all()
    assert len(target_rows_after) == 48
    assert all(row.quarantined for row in target_rows_after)
    assert {(r.source_listing_no, r.unit_price, r.title) for r in target_rows_after} == target_snapshot

    # 隔离挂牌不参与去重簇/均价/工单/导出
    assert session.scalar(
        select(func.count()).select_from(Listing).where(
            Listing.source_id == target.id, Listing.cluster_id.is_not(None)
        )
    ) == 0
    # 该源的工单行在库里原样保留（隔离只是查询口径隐藏，不能删历史/人工工单）
    visible_flags = (
        select(PriceFlag.id).join(Listing, Listing.id == PriceFlag.listing_id)
        .where(Listing.quarantined.is_(False))
    )
    quarantined_flag_leak = session.scalar(
        select(func.count())
        .select_from(PriceFlag)
        .join(Listing, Listing.id == PriceFlag.listing_id)
        .where(Listing.source_id == target.id, PriceFlag.id.in_(visible_flags))
    )
    assert quarantined_flag_leak == 0
    export_rows = export_service.rows_for_export(session)
    assert all(row[5] != target.name for row in export_rows)

    # 其它源完全不受影响（没有被纳入本次运行）
    assert session.scalar(
        select(func.count()).select_from(Listing).where(
            Listing.source_id == other.id, Listing.quarantined.is_(True)
        )
    ) == 0


def test_partial_page_isolation_then_full_rerun_restores(db, monkeypatch) -> None:
    session, platforms = db
    _set_fault(monkeypatch, "")
    _seed_full_snapshot(session, platforms)
    target = session.scalar(select(Source).where(Source.code == "agent_moments"))

    _set_fault(monkeypatch, "agent_moments:partial_page")
    run_bad = ingest_service.run_ingest(session, source_ids=[target.id], operator_email="a@b.io")
    batch_bad = ingest_service.list_batches_by_run(session, run_bad.id)[0]
    assert batch_bad["status"] == SourceBatchStatus.ISOLATED.value
    assert batch_bad["reason"] == "page_incomplete"
    assert 0 < batch_bad["pages_fetched"] < batch_bad["pages_expected"]
    assert session.scalar(
        select(func.count()).select_from(Listing).where(
            Listing.source_id == target.id, Listing.quarantined.is_(True)
        )
    ) == 48

    # 故障解除后重跑：完整快照原子替换，隔离解除且条数恢复
    _set_fault(monkeypatch, "")
    run_ok = ingest_service.run_ingest(session, source_ids=[target.id], operator_email="a@b.io")
    batch_ok = ingest_service.list_batches_by_run(session, run_ok.id)[0]
    assert batch_ok["status"] == SourceBatchStatus.REPLACED.value
    assert batch_ok["replaced_count"] == 48
    assert batch_ok["deleted_count"] == 0
    assert session.scalar(
        select(func.count()).select_from(Listing).where(
            Listing.source_id == target.id, Listing.quarantined.is_(True)
        )
    ) == 0
    assert run_ok.summary["recomputed"] is True


def test_rerun_same_snapshot_is_idempotent(db, monkeypatch) -> None:
    session, platforms = db
    _set_fault(monkeypatch, "")
    _seed_full_snapshot(session, platforms)

    first = ingest_service.run_ingest(session, operator_email="a@b.io")
    assert all(
        batch["status"] == SourceBatchStatus.UNCHANGED.value
        for batch in ingest_service.list_batches_by_run(session, first.id)
    )
    clusters_after_first = session.scalar(select(func.count()).select_from(ListingCluster))

    second = ingest_service.run_ingest(session, operator_email="a@b.io")
    assert all(
        batch["status"] == SourceBatchStatus.UNCHANGED.value
        for batch in ingest_service.list_batches_by_run(session, second.id)
    )
    assert second.summary["recomputed"] is False
    # 两次重复运行之间簇数、挂牌数完全不变
    assert session.scalar(select(func.count()).select_from(ListingCluster)) == clusters_after_first
    assert session.scalar(select(func.count()).select_from(Listing)) == 240


def test_human_review_and_price_fix_survive_reingest_on_same_house(db, monkeypatch) -> None:
    """人工确认结果在房价更新/再次采集后仍对应原房，不得漂移。"""
    session, platforms = db
    _set_fault(monkeypatch, "")
    _seed_full_snapshot(session, platforms)

    flag = session.scalar(select(PriceFlag).where(PriceFlag.flag_type == "high"))
    listing = session.get(Listing, flag.listing_id)
    source = session.get(Source, listing.source_id)
    original_listing_id = listing.id
    natural_key = listing.source_listing_no

    # 人工复核 + 门店回价改单价
    flag.review_status = "confirmed"
    flag.review_note = "人工确认：试探价"
    listing.unit_price = listing.unit_price - 200
    session.flush()
    cluster_service.recompute(session)
    session.flush()

    # 再跑一次该来源的完整采集（fixture 快照未变 → unchanged，行 id 与复核态原样保留）
    run = ingest_service.run_ingest(session, source_ids=[source.id], operator_email="a@b.io")
    batch = next(
        batch for batch in ingest_service.list_batches_by_run(session, run.id)
        if batch["source_id"] == source.id
    )
    assert batch["status"] == SourceBatchStatus.UNCHANGED.value
    refreshed = session.scalar(
        select(Listing).where(
            Listing.source_id == source.id, Listing.source_listing_no == natural_key
        )
    )
    assert refreshed.id == original_listing_id  # 行 id 不漂移
    refreshed_flag = session.scalar(select(PriceFlag).where(PriceFlag.listing_id == original_listing_id))
    assert refreshed_flag is not None
    assert refreshed_flag.review_status == "confirmed"
    assert refreshed_flag.review_note == "人工确认：试探价"
    assert refreshed.unit_price == listing.unit_price


def test_snapshot_change_replaces_rows_but_keeps_stable_natural_keys(db, monkeypatch) -> None:
    """快照内容变化（模拟平台调价）：原地更新同自然键行，id 不变，消失行才删除。"""
    session, platforms = db
    _set_fault(monkeypatch, "")
    _seed_full_snapshot(session, platforms)
    source = session.scalar(select(Source).where(Source.code == "lianjia_agg"))
    first_listing = session.scalar(
        select(Listing).where(Listing.source_id == source.id).order_by(Listing.id)
    )
    stable_id = first_listing.id
    stable_no = first_listing.source_listing_no

    # 直接篡改平台副本里该源第一条的单价，并删掉最后一条 → 哈希变化
    payload = fetch_service.load_platforms()
    bucket = payload["platforms"]["lianjia_agg"]
    bucket["pages"][0]["items"][0]["unit_price_yuan"] = (
        int(bucket["pages"][0]["items"][0]["unit_price_yuan"]) + 1234
    )
    removed_item = bucket["pages"][-1]["items"].pop()
    removed_no = removed_item["house_code"]

    run = ingest_service.run_ingest(session, source_ids=[source.id], operator_email="a@b.io")
    batch = ingest_service.list_batches_by_run(session, run.id)[0]
    assert batch["status"] == SourceBatchStatus.REPLACED.value
    assert batch["deleted_count"] == 1
    # 同自然键的行原地更新，主键不漂移
    updated = session.scalar(
        select(Listing).where(
            Listing.source_id == source.id, Listing.source_listing_no == stable_no
        )
    )
    assert updated.id == stable_id
    # 消失的挂牌连同其工单一起被原子删除
    assert session.scalar(
        select(Listing).where(
            Listing.source_id == source.id, Listing.source_listing_no == removed_no
        )
    ) is None
    assert run.summary["recomputed"] is True


def test_empty_snapshot_is_isolated(db, monkeypatch) -> None:
    session, platforms = db
    _set_fault(monkeypatch, "")
    _seed_full_snapshot(session, platforms)
    target = session.scalar(select(Source).where(Source.code == "owner_bbs"))

    _set_fault(monkeypatch, "owner_bbs:empty")
    run = ingest_service.run_ingest(session, source_ids=[target.id], operator_email="a@b.io")
    batch = ingest_service.list_batches_by_run(session, run.id)[0]
    assert batch["status"] == SourceBatchStatus.ISOLATED.value
    assert batch["reason"] == "empty_snapshot"
    assert all(
        row.quarantined
        for row in session.scalars(select(Listing).where(Listing.source_id == target.id)).all()
    )


def test_quarantined_listing_rejects_review_and_price_fix(db, monkeypatch) -> None:
    from src.utils.errors import AppError

    session, platforms = db
    _set_fault(monkeypatch, "")
    _seed_full_snapshot(session, platforms)
    target = session.scalar(select(Source).where(Source.code == "anjuke_portal"))
    _set_fault(monkeypatch, "anjuke_portal:crash")
    ingest_service.run_ingest(session, source_ids=[target.id], operator_email="a@b.io")

    quarantined = session.scalar(
        select(Listing).where(Listing.source_id == target.id).order_by(Listing.id)
    )
    from src.services import listing_service

    with pytest.raises(AppError) as price_exc:
        listing_service.fix_price(session, quarantined.id, 99999, "隔离期试图改价")
    assert price_exc.value.code == "SOURCE_QUARANTINED"

    flag = session.scalar(select(PriceFlag).where(PriceFlag.listing_id == quarantined.id))
    if flag is not None:
        from src.services import flag_service

        with pytest.raises(AppError) as review_exc:
            flag_service.review(session, flag.id, "confirmed", "隔离期复核", "a@b.io")
        assert review_exc.value.code == "SOURCE_QUARANTINED"
