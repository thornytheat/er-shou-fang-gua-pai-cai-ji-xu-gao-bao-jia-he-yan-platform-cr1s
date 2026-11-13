"""HTTP 端到端：真实路由 + RBAC + 按来源完整落批（SQLite 内存库 + 依赖覆盖）。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.config import database as dbmod
from src.config import settings as settings_module
from src.main import app
from src.models import Base
from src.models.listing import Listing
from src.models.price_flag import PriceFlag
from src.models.source import Source
from src.services import cluster_service, fetch_service, ingest_service

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures"
ANALYST = {"email": "analyst@rentlens.io", "password": "Demo@2026"}
CLIENT_USER = {"email": "client@rentlens.io", "password": "Demo@2026"}


@pytest.fixture()
def client(monkeypatch):
    from src.config import app as app_config

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    monkeypatch.setattr(dbmod, "SessionLocal", Session)
    monkeypatch.setattr(dbmod, "engine", engine)
    # lifespan 不能碰 MySQL：建库钩子换成内存库，自动 seed 关闭（测试自己灌数）
    monkeypatch.setattr(app_config, "wait_for_db", lambda *a, **k: True)
    monkeypatch.setattr(app_config, "engine", engine)
    monkeypatch.setattr(settings_module.settings, "seed_demo", False)
    # 故障注入默认关闭
    monkeypatch.setattr(settings_module.settings, "fault_injection", "")

    platforms = json.loads((FIXTURE_ROOT / "platforms.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(fetch_service, "load_platforms", lambda: platforms)
    monkeypatch.setattr("src.services.ingest_service.fetch_service.load_platforms", lambda: platforms)

    def _override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[dbmod.get_db] = _override_get_db

    # seed 同款初始数据
    import scripts.seed_demo as seed

    with Session() as db:
        seed.ensure_users(db)
        seed.ensure_sources(db)
        per_source = seed.ensure_listings(db)
        cluster_service.recompute(db)
        # 造一个 run 作为 source_batches 的外键宿主
        from src.constants.enums import IngestStatus, TriggerKind
        from src.models.ingest_run import IngestRun
        from src.utils.timeutil import utcnow

        run = IngestRun(
            run_no="RUN-SEED-01", trigger_kind=TriggerKind.SEED.value,
            status=IngestStatus.SUCCESS.value, sources_total=5, started_at=utcnow(),
            finished_at=utcnow(),
        )
        db.add(run)
        db.flush()
        seed.ensure_source_batches(db, per_source, run)
        seed.ensure_history_runs(db)
        seed.ensure_seed_audit(db)
        db.commit()

    with TestClient(app) as test_client:
        yield test_client, Session, platforms

    app.dependency_overrides.clear()
    engine.dispose()


def _login(test_client: TestClient, who: dict) -> str:
    resp = test_client.post("/api/auth/login", json=who)
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def test_client_role_cannot_run_ingest(client) -> None:
    test_client, _, _ = client
    token = _login(test_client, CLIENT_USER)
    resp = test_client.post(
        "/api/ingest-runs", json={"source_ids": None},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"


def test_isolated_source_end_to_end(client, monkeypatch) -> None:
    test_client, Session, platforms = client
    token = _login(test_client, ANALYST)
    headers = {"Authorization": f"Bearer {token}"}

    with Session() as db:
        target = db.scalar(select(Source).where(Source.code == "anjuke_portal"))
        target_id = target.id
        from src.services import export_service

        before_export = len(export_service.rows_for_export(db))
        before_flags = db.scalar(select(func.count()).select_from(PriceFlag))

    # 1) 注入 crash 跑采集
    monkeypatch.setattr(settings_module.settings, "fault_injection", "anjuke_portal:crash")
    resp = test_client.post(
        "/api/ingest-runs", json={"source_ids": [target_id]}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    run = resp.json()
    assert run["status"] == "failed"
    assert run["summary"]["isolated_total"] == 48

    # 2) 逐源落批明细接口：隔离 48 条、原因 fetch_crash、未改写
    batches_resp = test_client.get(f"/api/ingest-runs/{run['id']}/batches", headers=headers)
    assert batches_resp.status_code == 200
    batch = batches_resp.json()["items"][0]
    assert batch["status"] == "isolated"
    assert batch["reason"] == "fetch_crash"
    assert batch["isolated_count"] == 48
    assert batch["replaced_count"] == 0

    # 3) 该源挂牌全部隔离但一条没少
    with Session() as db:
        states = db.execute(
            select(Listing.quarantined, func.count())
            .where(Listing.source_id == target_id)
            .group_by(Listing.quarantined)
        ).all()
        state_map = {row[0]: row[1] for row in states}
        assert state_map.get(True) == 48
        assert state_map.get(False) is None

    # 4) 隔离挂牌不在导出里，且工单总数下降（隔离源工单不进队列）
    from src.services import export_service

    with Session() as db:
        export_rows = export_service.rows_for_export(db)
        target_name = db.get(Source, target_id).name
        assert all(row[5] != target_name for row in export_rows)
        assert len(export_rows) < before_export
        visible_flags = (
            select(PriceFlag.id).join(Listing, Listing.id == PriceFlag.listing_id)
            .where(Listing.quarantined.is_(False))
        )
        assert db.scalar(select(func.count()).select_from(visible_flags.subquery())) <= before_flags

    # 5) 隔离期改价被服务端拒绝（409 SOURCE_QUARANTINED）
    with Session() as db:
        quarantined_id = db.scalar(
            select(Listing.id).where(Listing.source_id == target_id).order_by(Listing.id)
        )
    fix_resp = test_client.patch(
        f"/api/listings/{quarantined_id}/price",
        json={"unit_price": 58000, "note": "隔离期试图改价应被拒绝"},
        headers=headers,
    )
    assert fix_resp.status_code == 409
    assert fix_resp.json()["code"] == "SOURCE_QUARANTINED"

    # 6) 故障解除重跑 → 原子替换、隔离解除
    monkeypatch.setattr(settings_module.settings, "fault_injection", "")
    rerun = test_client.post(
        "/api/ingest-runs", json={"source_ids": [target_id]}, headers=headers
    ).json()
    assert rerun["summary"]["source_batches"][0]["status"] == "replaced"
    with Session() as db:
        assert db.scalar(
            select(func.count()).select_from(Listing).where(
                Listing.source_id == target_id, Listing.quarantined.is_(True)
            )
        ) == 0


def test_idempotent_rerun_does_not_recompute(client) -> None:
    test_client, _, _ = client
    token = _login(test_client, ANALYST)
    headers = {"Authorization": f"Bearer {token}"}
    first = test_client.post("/api/ingest-runs", json={"source_ids": None}, headers=headers).json()
    assert all(b["status"] == "unchanged" for b in first["summary"]["source_batches"])
    assert first["summary"]["recomputed"] is False
    second = test_client.post("/api/ingest-runs", json={"source_ids": None}, headers=headers).json()
    assert second["summary"]["recomputed"] is False
    assert second["created_count"] == 0 and second["updated_count"] == 0
