"""Celery 入口：backend 投递任务，worker 容器消费（beat 写心跳 + 每天 08:30 自动采集）。"""
from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from src.config.settings import settings

celery_app = Celery(
    "rentlens",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["src.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=False,
    task_track_started=True,
    result_expires=3600,
    broker_connection_retry_on_startup=True,
    worker_hijack_root_logger=False,
)

celery_app.conf.beat_schedule = {
    "rentlens-heartbeat": {"task": "rentlens.heartbeat", "schedule": 10.0},
    "rentlens-daily-ingest": {"task": "rentlens.scheduled_ingest", "schedule": crontab(hour=8, minute=30)},
}

TASK_HEARTBEAT = "rentlens.heartbeat"
TASK_SCHEDULED_INGEST = "rentlens.scheduled_ingest"
TASK_RECOMPUTE = "rentlens.recompute_clusters"
