"""Router de páginas web (UI Jinja2 + HTMX).

Páginas: landing, dashboard, historial, login, register, logout.
Las páginas de documentos viven en routers/documents.py.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Form, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.service import AuthError, login_user, register_user
from app.deps import get_current_user_optional, get_db, require_user
from app.models.document import DocStatus, DocType, Document
from app.models.user import User

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


# ---------- Landing ----------

@router.get("/")
def index(
    request: Request,
    user: User | None = Depends(get_current_user_optional),
):
    if user:
        return RedirectResponse("/app", status_code=303)
    return templates.TemplateResponse("index.html", {"request": request, "user": None})


@router.get("/app")
def dashboard(
    request: Request,
    user: User = Depends(get_current_user_optional),  # type: ignore[assignment]
):
    if user is None:
        return RedirectResponse("/auth/login", status_code=303)
    return templates.TemplateResponse(
        "dashboard.html", {"request": request, "user": user, "section": "dashboard"}
    )


# ---------- Historial ----------

# Duplicamos los helpers de documents.py para evitar dependencia circular.
_DOC_TYPE_LABELS = {
    DocType.INVOICE: "Factura",
    DocType.RECEIPT: "Remito",
    DocType.QUOTE: "Presupuesto",
    DocType.CONTRACT: "Contrato",
    DocType.REPORT: "Informe",
    DocType.TABLE: "Tabla",
    DocType.GENERIC: "Genérico",
}

_STATUS_LABELS = {
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
    return _DOC_TYPE_LABELS.get(dt, dt.value)


def _status_badge(status_val: DocStatus | str) -> str:
    if isinstance(status_val, str):
        status_val = DocStatus(status_val)
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
        f'{colors.get(status_val, "bg-slate-100 text-slate-600")}">'
        f'{_STATUS_LABELS.get(status_val, status_val.value)}</span>'
    )


@router.get("/app/history")
def history(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
    status_filter: str | None = Query(None, alias="status"),
    doc_type: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    """Historial de todos los documentos del usuario con filtros."""
    query = select(Document).where(Document.user_id == user.id)

    # Filtro por estado
    if status_filter:
        try:
            query = query.where(Document.status == DocStatus(status_filter))
        except ValueError:
            pass

    # Filtro por tipo de documento
    if doc_type:
        try:
            query = query.where(Document.doc_type == DocType(doc_type))
        except ValueError:
            pass

    # Filtro por rango de fechas
    if date_from:
        try:
            dt_from = date.fromisoformat(date_from)
            query = query.where(func.date(Document.created_at) >= dt_from)
        except ValueError:
            pass

    if date_to:
        try:
            dt_to = date.fromisoformat(date_to)
            query = query.where(func.date(Document.created_at) <= dt_to)
        except ValueError:
            pass

    # Contar total con filtros aplicados
    count_query = select(func.count()).select_from(query.subquery())
    total = db.execute(count_query).scalar() or 0

    # Paginación
    offset = (page - 1) * per_page
    docs = list(
        db.execute(
            query.order_by(Document.created_at.desc()).offset(offset).limit(per_page)
        ).scalars()
    )

    total_pages = max(1, (total + per_page - 1) // per_page)

    return templates.TemplateResponse(
        "documents/history.html",
        {
            "request": request,
            "user": user,
            "documents": docs,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "status_filter": status_filter or "",
            "doc_type_filter": doc_type or "",
            "date_from": date_from or "",
            "date_to": date_to or "",
            "doc_type_label": _doc_type_label,
            "status_badge": _status_badge,
            "status_options": list(DocStatus),
            "doc_type_options": list(DocType),
            "section": "history",
        },
    )


# ---------- Login / Register ----------

@router.get("/auth/login")
def login_form(
    request: Request,
    user: User | None = Depends(get_current_user_optional),
):
    if user:
        return RedirectResponse("/app", status_code=303)
    return templates.TemplateResponse(
        "auth/login.html", {"request": request, "user": None, "error": None}
    )


@router.post("/auth/login")
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        user, token = login_user(db, username, password)
    except AuthError as e:
        return templates.TemplateResponse(
            "auth/login.html",
            {"request": request, "user": None, "error": e.message},
            status_code=e.status_code,
        )
    resp = RedirectResponse("/app", status_code=303)
    resp.set_cookie(
        key="access_token",
        value=f"Bearer {token}",
        httponly=True,
        samesite="lax",
        secure=False,  # en prod con HTTPS setear True vía settings
        max_age=60 * 60 * 24 * 7,
    )
    return resp


@router.get("/auth/register")
def register_form(
    request: Request,
    user: User | None = Depends(get_current_user_optional),
):
    if user:
        return RedirectResponse("/app", status_code=303)
    return templates.TemplateResponse(
        "auth/register.html", {"request": request, "user": None, "error": None}
    )


@router.post("/auth/register")
def register_submit(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(""),
    db: Session = Depends(get_db),
):
    from app.schemas.auth import UserCreate

    try:
        from pydantic import ValidationError

        data = UserCreate(
            username=username, email=email, password=password, full_name=full_name
        )
        register_user(db, data)
    except ValidationError as e:
        msg = "; ".join(f"{'/'.join(loc)}: {err['msg']}" for loc, err in zip(
            (tuple(err["loc"]) for err in e.errors()), e.errors()
        ))
        # Más simple: primer mensaje
        msg = e.errors()[0]["msg"] if e.errors() else "Datos inválidos."
        return templates.TemplateResponse(
            "auth/register.html",
            {"request": request, "user": None, "error": msg},
            status_code=400,
        )
    except AuthError as e:
        return templates.TemplateResponse(
            "auth/register.html",
            {"request": request, "user": None, "error": e.message},
            status_code=e.status_code,
        )
    # Login automático tras registro
    from app.auth.service import login_user

    user, token = login_user(db, username, password)
    resp = RedirectResponse("/app", status_code=303)
    resp.set_cookie(
        key="access_token",
        value=f"Bearer {token}",
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
    )
    return resp


@router.post("/auth/logout")
def logout():
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie("access_token")
    return resp


@router.get("/auth/logout")
def logout_get():
    return logout()
