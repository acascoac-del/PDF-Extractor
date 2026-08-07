"""Tarea de Celery: ejecuta el pipeline de extracción completo."""
from __future__ import annotations

import logging

from app.database import SessionLocal
from app.models.document import DocStatus, Document
from app.services.classification import run_pipeline_sync
from app.services.storage import abs_path_for
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=30)
def process_document(self, document_id: str) -> dict:
    """Procesa un documento de forma asíncrona: texto → clasificar → extraer."""
    db = SessionLocal()
    try:
        doc = db.get(Document, document_id)
        if doc is None:
            return {"error": "Documento no encontrado", "document_id": document_id}

        doc.celery_task_id = self.request.id
        db.commit()

        pdf_path = abs_path_for(doc.upload_path)
        run_pipeline_sync(doc, pdf_path, db, user=doc.user)

        return {
            "document_id": document_id,
            "status": doc.status.value,
            "doc_type": doc.doc_type.value if doc.doc_type else None,
        }
    except Exception as exc:
        logger.exception("Error procesando documento %s", document_id)
        try:
            doc = db.get(Document, document_id)
            if doc:
                doc.status = DocStatus.FAILED
                doc.error_message = str(exc)[:500]
                db.commit()
        except Exception:
            pass
        raise self.retry(exc=exc)
    finally:
        db.close()
