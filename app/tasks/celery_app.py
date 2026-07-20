"""Configuración de Celery."""
from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "pdf_extractor",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks.pipeline", "app.tasks.cleanup"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone=settings.timezone,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # Tareas periódicas (Celery Beat)
    beat_schedule={
        "cleanup-expired-documents": {
            "task": "app.tasks.cleanup.cleanup_expired",
            "schedule": crontab(hour=settings.cleanup_cron_hour, minute=0),
        },
    },
)
