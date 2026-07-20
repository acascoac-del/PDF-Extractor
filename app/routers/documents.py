"""Router de documentos: upload, listado, detalle, clasificación, exportación (UI).

Todo lo que sea la interfaz web de documentos (HTMX partials + páginas completas).
La API REST v1 vive en routers/api.py.

Adaptado para Vercel: procesamiento síncrono, almacenamiento en R2 o local.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.deps import get_current_user_optional, get_db, require_user
from app.models.document import DocStatus, DocType, Document
from app.models.extraction import Extraction
from app.models.user import User
from app.services.storage import abs_path_for, save_upload, read_file
from app.services.pdf_text import extract_text
from app.services.limits import check_pdf_limit, increment_pdf_count

router = APIRouter(prefix="/app/documents")
templates = Jinja2Templates(directory="app/templates")

# Mapa de tipos en español para la UI
DOC_TYPE_LABELS = {
    DocType.INVOICE: "Factura",
    DocType.RECEIPT: "Remito",
    DocType.QUOTE: "Presupuesto",
    DocType.CONTRACT: "Contrato",
    DocType.REPORT: "Informe",
    DocType.TABLE: "Tabla",
    DocType.GENERIC: "Genérico",
}

STATUS_LABELS = {
    DocStatus.UPLOADED: "Subido",
    DocStatus.CLASSIFIED: "Clasificado",
    DocStatus.QUEUED: "En cola",
    DocStatus.PROCESSING: "Procesando",
    DocStatus.EXTRACTED: "Extraído",
    DocStatus.COMPLETED: "Completado",
    DocStatus.FAILED: "Error",
}


def _doc_type_label(dt: DocType | str | None) -> str:
    if dt is None:
        return "—"
    if isinstance(dt, str):
        dt = DocType(dt)
    return DOC_TYPE_LABELS.get(dt, dt.value)


def _status_badge(status: DocStatus | str) -> str:
    if isinstance(status, str):
        status = DocStatus(status)
    colors = {
        DocStatus.UPLOADED: "bg-slate-100 text-slate-600",
        DocStatus.CLASSIFIED: "bg-blue-100 text-blue-700",
        DocStatus.QUEUED: "bg-amber-100 text-amber-700",
        DocStatus.PROCESSING: "bg-amber-100 text-amber-700 animate-pulse",
        DocStatus.EXTRACTED: "bg-green-100 text-green-700",
        DocStatus.COMPLETED: "bg-green-100 text-green-700",
        DocStatus.FAILED: "bg-red-100 text-red-700",
    }
    return (
        f'<span class="inline-block px-2 py-0.5 rounded-full text-xs font-medium '
        f'{colors.get(status, "bg-slate-100 text-slate-600")}">'
        f'{STATUS_LABELS.get(status, status.value)}</span>'
    )


# ============ Páginas ============

@router.get("/new")
def new_upload_form(
    request: Request,
    user: User = Depends(require_user),
):
    return templates.TemplateResponse(
        "documents/new.html",
        {"request": request, "user": user, "max_mb": settings.max_upload_mb},
    )


@router.post("/upload", response_class=HTMLResponse)
async def upload_files(
    request: Request,
    files: list[UploadFile] = File(...),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Sube uno o más PDFs. Devuelve partial con resultado."""
    results: list[dict] = []
    errors: list[str] = []

    for f in files:
        if not f.filename:
            continue
        # Validar extensión
        if not f.filename.lower().endswith(".pdf"):
            errors.append(f"{f.filename}: solo se permiten archivos PDF.")
            continue
        # Validar tamaño
        content = await f.read()
        if len(content) > settings.max_upload_bytes:
            errors.append(
                f"{f.filename}: supera el límite de {settings.max_upload_mb} MB."
            )
            continue

        stored_name, rel_path = save_upload(content, f.filename)
        doc = Document(
            user_id=user.id,
            original_filename=f.filename,
            stored_filename=stored_name,
            size_bytes=len(content),
            upload_path=rel_path,
            status=DocStatus.UPLOADED,
        )
        db.add(doc)
        db.flush()  # para tener el id
        results.append(
            {"id": doc.id, "filename": f.filename, "size": len(content), "status": "uploaded"}
        )

    db.commit()

    # Hacer detección rápida de páginas y escaneado para cada documento subido
    for r in results:
        doc = db.get(Document, r["id"])
        try:
            # Leer PDF desde R2 o local
            pdf_bytes = read_file(doc.upload_path)
            pdf_content = extract_text(pdf_bytes)
            doc.page_count = pdf_content.page_count
            doc.is_scanned = pdf_content.is_scanned
            doc.needs_ocr = pdf_content.is_scanned
        except Exception as e:
            doc.error_message = f"Error al leer PDF: {e}"
            doc.status = DocStatus.FAILED
        db.commit()

    return templates.TemplateResponse(
        "documents/upload_results.html",
        {
            "request": request,
            "user": user,
            "results": results,
            "errors": errors,
        },
    )


@router.get("/list")
def document_list(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
    page: int = 1,
    per_page: int = 20,
):
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

    return templates.TemplateResponse(
        "documents/list.html",
        {
            "request": request,
            "user": user,
            "documents": docs,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": range(1, (total // per_page) + 2),
            "doc_type_label": _doc_type_label,
            "status_badge": _status_badge,
        },
    )


@router.get("/recent", response_class=HTMLResponse)
def recent_docs_partial(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Partial HTMX: filas de los 10 documentos más recientes (para el dashboard)."""
    docs = list(
        db.execute(
            select(Document)
            .where(Document.user_id == user.id)
            .order_by(Document.created_at.desc())
            .limit(10)
        ).scalars()
    )
    return templates.TemplateResponse(
        "documents/recent_partial.html",
        {
            "request": request,
            "user": user,
            "documents": docs,
            "doc_type_label": _doc_type_label,
            "status_badge": _status_badge,
        },
    )


@router.get("/detail/{doc_id}")
def document_detail(
    request: Request,
    doc_id: str,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    doc = db.execute(
        select(Document).where(Document.id == doc_id, Document.user_id == user.id)
    ).scalar_one_or_none()
    if doc is None:
        raise HTTPException(404, "Documento no encontrado.")

    extraction = None
    if doc.extraction:
        extraction = doc.extraction

    return templates.TemplateResponse(
        "documents/detail.html",
        {
            "request": request,
            "user": user,
            "doc": doc,
            "extraction": extraction,
            "doc_type_label": _doc_type_label,
            "status_badge": _status_badge,
        },
    )


@router.post("/classify/{doc_id}")
def classify_document(
    request: Request,
    doc_id: str,
    doc_type: str = Form(...),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """El usuario confirma/corregie la clasificación y lanza el procesamiento."""
    # Verificar limite de PDFs antes de procesar
    can_process, used, limit = check_pdf_limit(user)
    if not can_process:
        return RedirectResponse("/app/pricing?limit=1", status_code=303)

    doc = db.execute(
        select(Document).where(Document.id == doc_id, Document.user_id == user.id)
    ).scalar_one_or_none()
    if doc is None:
        raise HTTPException(404)

    try:
        doc.doc_type = DocType(doc_type)
    except ValueError:
        raise HTTPException(400, f"Tipo inválido: {doc_type}")

    doc.doc_type_source = "user"
    doc.doc_type_confidence = 1.0
    doc.status = DocStatus.QUEUED

    # Procesamiento síncrono (compatible con Vercel serverless)
    db.commit()

    from app.services.classification import run_pipeline_sync

    try:
        # Leer PDF desde R2 o local
        pdf_bytes = read_file(doc.upload_path)
        run_pipeline_sync(doc, pdf_bytes, db, user=user)
        # Incrementar contador de PDFs procesados
        increment_pdf_count(user, db)
    except Exception as e:
        doc.status = DocStatus.FAILED
        doc.error_message = str(e)
        db.commit()

    return RedirectResponse(f"/app/documents/detail/{doc_id}", status_code=303)


@router.delete("/delete/{doc_id}", response_class=HTMLResponse)
def delete_document(
    doc_id: str,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    doc = db.execute(
        select(Document).where(Document.id == doc_id, Document.user_id == user.id)
    ).scalar_one_or_none()
    if doc is None:
        return HTMLResponse("<div class='text-red-600 text-sm'>Documento no encontrado.</div>", 404)

    from app.services.storage import delete_file

    delete_file(doc.upload_path)
    db.delete(doc)
    db.commit()
    return HTMLResponse("")


@router.get("/{doc_id}/preview")
def preview_pdf(
    doc_id: str,
    page: int = 0,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Devuelve el PDF como response inline para el visor del navegador."""
    doc = db.execute(
        select(Document).where(Document.id == doc_id, Document.user_id == user.id)
    ).scalar_one_or_none()
    if doc is None:
        raise HTTPException(404)

    try:
        pdf_bytes = read_file(doc.upload_path)
    except FileNotFoundError:
        raise HTTPException(404, "Archivo no encontrado.")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={doc.original_filename}"},
    )


@router.post("/{doc_id}/correct", response_class=HTMLResponse)
async def correct_field(
    request: Request,
    doc_id: str,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Endpoint HTMX: guarda una corrección de campo inline (feedback loop)."""
    doc = db.execute(
        select(Document).where(Document.id == doc_id, Document.user_id == user.id)
    ).scalar_one_or_none()
    if doc is None or doc.extraction is None:
        return HTMLResponse("")

    form = await request.form()
    for key, value in form.items():
        if not key or key == "csrf_token":
            continue
        fields = doc.extraction.data.get("fields", {})
        field = fields.get(key, {})
        old_value = field.get("value")
        new_value = value if value else None

        if old_value != new_value:
            # Guardar corrección en tabla
            from app.models.correction import Correction

            correction = Correction(
                document_id=doc.id,
                user_id=user.id,
                field_key=key,
                original_value=str(old_value) if old_value is not None else None,
                corrected_value=new_value,
                original_confidence=field.get("confidence"),
            )
            db.add(correction)

            # Actualizar el valor en la extracción
            fields[key] = {
                "value": new_value,
                "source": "user",
                "confidence": 1.0,
                "raw": new_value,
            }
            doc.extraction.data["fields"] = fields

    db.commit()
    # Devolver el badge actualizado
    return HTMLResponse(
        '<span class="inline-block px-1.5 py-0.5 rounded text-xs font-medium conf-high">user · 100%</span>'
    )
