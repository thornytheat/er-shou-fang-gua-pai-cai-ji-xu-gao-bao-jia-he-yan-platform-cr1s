from __future__ import annotations

from fastapi import APIRouter

from src.config.database import ping_db
from src.config.settings import settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    db_ok = ping_db()
    redis_ok = False
    worker_ok = False
    try:
        import time

        import redis

        client = redis.Redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=1)
        client.ping()
        redis_ok = True
        heartbeat = client.get("rentlens:worker:heartbeat")
        worker_ok = bool(heartbeat) and (time.time() - float(heartbeat)) < 120
    except Exception:  # noqa: BLE001
        redis_ok = False
    return {
        "status": "ok" if db_ok and redis_ok else "degraded",
        "db": db_ok,
        "redis": redis_ok,
        "worker": worker_ok,
        "service": "rentlens-backend",
    }
