"""Tarea de Celery Beat: borrado automático de documentos vencidos."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.models.document import Document
from app.services.storage import delete_file
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task
def cleanup_expired() -> dict:
    """Borra documentos cuyo expires_at ya pasó o que llevan más de AUTO_DELETE_DAYS."""
    if settings.auto_delete_days <= 0:
        return {"deleted": 0, "reason": "auto_delete disabled"}

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=settings.auto_delete_days)

        # Documentos con expires_at ya pasado
        q1 = select(Document).where(Document.expires_at != None, Document.expires_at < now)
        # Documentos sin expires_at pero más viejos que auto_delete_days
        q2 = select(Document).where(Document.expires_at == None, Document.created_at < cutoff)

        seen_ids: set[str] = set()
        count = 0
        for q in (q1, q2):
            for doc in db.execute(q).scalars():
                if doc.id in seen_ids:
                    continue
                seen_ids.add(doc.id)
                delete_file(doc.upload_path)
                db.delete(doc)
                count += 1

        db.commit()
        logger.info("Cleanup: eliminados %d documentos vencidos", count)
        return {"deleted": count}
    finally:
        db.close()
