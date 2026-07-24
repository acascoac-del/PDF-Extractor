"""API REST v1: endpoints JSON para integracion programatica.

Todos los endpoints requieren autenticacion via Bearer token (JWT o API key).
Prefijo: /api/v1

Adaptado para Vercel: almacenamiento en R2 o local, procesamiento síncrono.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.deps import get_current_user_api, get_db
from app.models.document import DocStatus, DocType, Document
from app.models.extraction import Extraction
from app.models.user import User
from app.services.classification import run_pipeline_sync
from app.services.storage import abs_path_for, save_upload, read_file

router = APIRouter(prefix="/api/v1")


# ---------- Helpers ----------


def _serialize_doc(doc: Document) -> dict:
    """Serializa un documento a dict para respuestas JSON."""
    return {
        "id": doc.id,
        "filename": doc.original_filename,
        "doc_type": doc.doc_type.value if doc.doc_type else None,
        "status": doc.status.value,
        "page_count": doc.page_count,
        "size_bytes": doc.size_bytes,
        "is_scanned": doc.is_scanned,
        "needs_ocr": doc.needs_ocr,
        "doc_type_confidence": doc.doc_type_confidence,
        "doc_type_source": doc.doc_type_source,
        "error_message": doc.error_message,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
        "processed_at": doc.processed_at.isoformat() if doc.processed_at else None,
    }


def _serialize_extraction(extraction: Extraction) -> dict:
    """Serializa una extraccion a dict para respuestas JSON."""
    return {
        "id": extraction.id,
        "doc_type": extraction.doc_type,
        "data": extraction.data,
        "overall_confidence": extraction.overall_confidence,
        "llm_model": extraction.llm_model,
        "llm_primary": getattr(extraction, "llm_primary", False),
        "created_at": extraction.created_at.isoformat() if extraction.created_at else None,
        "updated_at": extraction.updated_at.isoformat() if extraction.updated_at else None,
    }


# ---------- Endpoints ----------


@router.get("/documents")
def list_documents(
    user: User = Depends(get_current_user_api),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1, description="Numero de pagina"),
    per_page: int = Query(20, ge=1, le=100, description="Documentos por pagina"),
):
    """Lista los documentos del usuario autenticado (paginado)."""
    offset = (page - 1) * per_page

    total = db.execute(
        select(func.count()).where(Document.user_id == user.id)
    ).scalar() or 0

    docs = list(
        db.execute(
            select(Document)
            .where(Document.user_id == user.id)
            .order_by(Document.created_at.desc())
            .offset(offset)
            .limit(per_page)
        ).scalars()
    )

    total_pages = max(1, (total + per_page - 1) // per_page)

    return {
        "items": [_serialize_doc(d) for d in docs],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
        },
    }


@router.post("/documents/upload", status_code=201)
async def upload_document(
    user: User = Depends(get_current_user_api),
    db: Session = Depends(get_db),
    file: UploadFile = File(..., description="Archivo PDF a subir"),
):
    """Sube un PDF y devuelve el documento creado con su ID."""
    if not file.filename:
        raise HTTPException(400, "El archivo debe tener un nombre.")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Solo se permiten archivos PDF.")

    content = await file.read()
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(
            413,
            f"El archivo supera el limite de {settings.max_upload_mb} MB.",
        )

    stored_name, rel_path = save_upload(content, file.filename)
    doc = Document(
        user_id=user.id,
        original_filename=file.filename,
        stored_filename=stored_name,
        size_bytes=len(content),
        upload_path=rel_path,
        status=DocStatus.UPLOADED,
    )
    db.add(doc)
    db.flush()

    # Deteccion rapida de paginas y escaneo
    try:
        from app.services.pdf_text import extract_text

        pdf_bytes = read_file(doc.upload_path)
        pdf_content = extract_text(pdf_bytes)
        doc.page_count = pdf_content.page_count
        doc.is_scanned = pdf_content.is_scanned
        doc.needs_ocr = pdf_content.is_scanned
    except Exception as e:
        doc.error_message = f"Error al leer PDF: {e}"
        doc.status = DocStatus.FAILED

    db.commit()
    db.refresh(doc)

    return {"document": _serialize_doc(doc)}


@router.get("/documents/{doc_id}")
def get_document(
    doc_id: str,
    user: User = Depends(get_current_user_api),
    db: Session = Depends(get_db),
):
    """Obtiene el detalle de un documento incluyendo datos de extraccion (si existe)."""
    doc = db.execute(
        select(Document).where(Document.id == doc_id, Document.user_id == user.id)
    ).scalar_one_or_none()
    if doc is None:
        raise HTTPException(404, "Documento no encontrado.")

    result = {"document": _serialize_doc(doc)}

    if doc.extraction:
        result["extraction"] = _serialize_extraction(doc.extraction)

    return result


@router.post("/documents/{doc_id}/extract")
def trigger_extraction(
    doc_id: str,
    user: User = Depends(get_current_user_api),
    db: Session = Depends(get_db),
):
    """Dispara la extraccion de datos de un documento."""
    doc = db.execute(
        select(Document).where(Document.id == doc_id, Document.user_id == user.id)
    ).scalar_one_or_none()
    if doc is None:
        raise HTTPException(404, "Documento no encontrado.")

    if doc.status == DocStatus.FAILED:
        # Permitir re-intento: resetear estado
        doc.status = DocStatus.UPLOADED
        doc.error_message = None

    if doc.status in (DocStatus.PROCESSING, DocStatus.QUEUED):
        raise HTTPException(
            409, "El documento ya esta siendo procesado."
        )

    # Eliminar extraccion previa si existe (re-extraccion)
    if doc.extraction:
        db.delete(doc.extraction)
        db.flush()

    try:
        pdf_bytes = read_file(doc.upload_path)
        run_pipeline_sync(doc, pdf_bytes, db)
    except Exception as e:
        doc.status = DocStatus.FAILED
        doc.error_message = str(e)
        db.commit()
        raise HTTPException(500, f"Error en la extraccion: {e}")

    db.refresh(doc)
    result = {"document": _serialize_doc(doc)}
    if doc.extraction:
        result["extraction"] = _serialize_extraction(doc.extraction)

    return result


@router.get("/documents/{doc_id}/export/{format}")
def export_document(
    doc_id: str,
    format: str,
    user: User = Depends(get_current_user_api),
    db: Session = Depends(get_db),
):
    """Exporta los datos extraidos en el formato solicitado (xlsx, docx, csv, json)."""
    allowed_formats = {"xlsx", "docx", "csv", "json"}
    if format not in allowed_formats:
        raise HTTPException(
            400,
            f"Formato no soportado: '{format}'. Use: {', '.join(sorted(allowed_formats))}",
        )

    doc = db.execute(
        select(Document).where(Document.id == doc_id, Document.user_id == user.id)
    ).scalar_one_or_none()
    if doc is None:
        raise HTTPException(404, "Documento no encontrado.")

    if doc.extraction is None:
        raise HTTPException(
            400, "El documento no tiene extraccion. Ejecute la extraccion primero."
        )

    # Generar nombre de archivo seguro
    stem = doc.original_filename.rsplit(".", 1)[0]
    safe_stem = "".join(c for c in stem[:80] if c.isalnum() or c in " -_")
    filename = f"{safe_stem}.{format}"

    if format == "xlsx":
        from app.services.exporters.excel import generate_excel

        buf = generate_excel(doc, doc.extraction)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif format == "docx":
        from app.services.exporters.word import generate_word

        buf = generate_word(doc, doc.extraction)
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif format == "csv":
        from app.services.exporters.csv_export import generate_csv

        buf = generate_csv(doc.extraction)
        media_type = "text/csv"
    elif format == "json":
        from app.services.exporters.json_export import generate_json

        buf = generate_json(doc.extraction)
        media_type = "application/json"

    return StreamingResponse(
        buf,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
