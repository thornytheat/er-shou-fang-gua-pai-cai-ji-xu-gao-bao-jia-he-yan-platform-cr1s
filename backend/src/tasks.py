"""Celery 任务：心跳、每天 08:30 自动采集、去重重算。"""
from __future__ import annotations

import time

from src.config.celery_app import celery_app
from src.config.settings import settings
from src.utils.logger import get_logger

logger = get_logger("tasks")


def _redis():
    import redis

    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


@celery_app.task(name="rentlens.heartbeat")
def heartbeat() -> str:
    try:
        _redis().set("rentlens:worker:heartbeat", time.time())
        return "ok"
    except Exception as exc:  # noqa: BLE001
        logger.warning("heartbeat failed: %s", exc)
        return "error"


@celery_app.task(name="rentlens.scheduled_ingest")
def scheduled_ingest() -> dict:
    """每天 08:30 的定时采集（与研究组的旧习惯对齐）。"""
    from src.config.database import session_scope
    from src.services import audit_service, ingest_service

    try:
        with session_scope() as db:
            run = ingest_service.run_ingest(
                db, trigger="schedule", operator_email="scheduler@rentlens.io"
            )
            audit_service.record(
                db,
                actor_email="scheduler@rentlens.io",
                actor_role="admin",
                action="ingest.schedule",
                entity="ingest_run",
                entity_id=run.id,
                detail={
                    "items": run.items_fetched,
                    "throttled": run.throttled_count,
                    "status": run.status,
                    "replaced": run.summary.get("replaced_total", 0),
                    "isolated": run.summary.get("isolated_total", 0),
                },
                layer="worker",
            )
            payload = {
                "run_no": run.run_no,
                "items": run.items_fetched,
                "created": run.created_count,
                "clusters": run.cluster_count,
                "flags": run.flag_count,
            }
        _redis().set("rentlens:last_scheduled_run", time.time())
        return payload
    except Exception as exc:  # noqa: BLE001
        logger.warning("scheduled ingest failed: %s", exc)
        return {"status": "error", "error": str(exc)}


@celery_app.task(name="rentlens.recompute_clusters")
def recompute_clusters() -> dict:
    from src.config.database import session_scope
    from src.services import cluster_service

    try:
        with session_scope() as db:
            result = cluster_service.recompute(db)
        return result
    except Exception as exc:  # noqa: BLE001
        logger.warning("recompute failed: %s", exc)
        return {"status": "error", "error": str(exc)}
