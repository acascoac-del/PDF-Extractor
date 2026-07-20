"""Router de exportación: genera y descarga Excel, Word, CSV, JSON, ZIP.

Los formatos se generan en demanda (no se cachean en disco por ahora;
en producción conviene cachear y limpiar).
"""
from __future__ import annotations

from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import get_db, require_user
from app.models.document import Document
from app.models.extraction import Extraction
from app.models.user import User
from app.services.exporters.excel import generate_excel
from app.services.exporters.word import generate_word
from app.services.exporters.csv_export import generate_csv
from app.services.exporters.json_export import generate_json
from app.services.exporters.batch_zip import generate_batch_zip

router = APIRouter(prefix="/app/documents")


@router.get("/{doc_id}/export/xlsx")
def export_xlsx(
    doc_id: str,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    doc = _get_doc_with_extraction(doc_id, user.id, db)
    buf = generate_excel(doc, doc.extraction)
    filename = _export_filename(doc, "xlsx")
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{doc_id}/export/docx")
def export_docx(
    doc_id: str,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    doc = _get_doc_with_extraction(doc_id, user.id, db)
    buf = generate_word(doc, doc.extraction)
    filename = _export_filename(doc, "docx")
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{doc_id}/export/csv")
def export_csv_endpoint(
    doc_id: str,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    doc = _get_doc_with_extraction(doc_id, user.id, db)
    buf = generate_csv(doc.extraction)
    filename = _export_filename(doc, "csv")
    return StreamingResponse(
        buf,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{doc_id}/export/json")
def export_json_endpoint(
    doc_id: str,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    doc = _get_doc_with_extraction(doc_id, user.id, db)
    buf = generate_json(doc.extraction)
    filename = _export_filename(doc, "json")
    return StreamingResponse(
        buf,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{doc_id}/export/zip")
def export_zip(
    doc_id: str,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    doc = _get_doc_with_extraction(doc_id, user.id, db)
    buf = generate_batch_zip(doc, doc.extraction)
    filename = _export_filename(doc, "zip")
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _get_doc_with_extraction(doc_id: str, user_id: str, db: Session) -> Document:
    doc = db.execute(
        select(Document).where(Document.id == doc_id, Document.user_id == user_id)
    ).scalar_one_or_none()
    if doc is None:
        raise HTTPException(404, "Documento no encontrado.")
    if doc.extraction is None:
        raise HTTPException(400, "El documento no tiene extracción todavía.")
    return doc


def _export_filename(doc: Document, ext: str) -> str:
    """Nombre del archivo de exportación basado en el original."""
    stem = doc.original_filename.rsplit(".", 1)[0]
    safe = "".join(c for c in stem[:80] if c.isalnum() or c in " -_")
    return f"{safe}.{ext}"
