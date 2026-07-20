"""Router de suscripcion: precios, checkout, webhooks, portal de cliente.

Utiliza Mercado Pago como procesador de pagos.
"""
from __future__ import annotations

import hashlib
import hmac
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import settings
from app.deps import get_db, get_current_user_optional, require_user
from app.models.user import User
from app.services.limits import check_pdf_limit, FREE_PDF_LIMIT

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


# ============ Pagina de precios ============

@router.get("/app/pricing", response_class=HTMLResponse)
def pricing_page(
    request: Request,
    limit: int = 0,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """Muestra los planes Free y Pro con el uso actual del usuario."""
    used = 0
    plan = "free"
    mp_public_key = settings.mp_public_key

    if user:
        can_process, used, _limit = check_pdf_limit(user)
        db.commit()  # guardar posible reset de contador
        plan = user.plan

    return templates.TemplateResponse(
        "pricing.html",
        {
            "request": request,
            "user": user,
            "plan": plan,
            "used": used,
            "free_limit": FREE_PDF_LIMIT,
            "limit_reached": limit == 1,
            "mp_public_key": mp_public_key,
        },
    )


# ============ Checkout de Mercado Pago ============

@router.post("/app/subscribe")
def subscribe(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Crea una preferencia de Mercado Pago y redirige al checkout."""
    if user.plan == "pro":
        return RedirectResponse("/app/pricing", status_code=303)

    base_url = str(request.base_url).rstrip("/")
    success_url = f"{base_url}/app/subscribe/success"
    failure_url = f"{base_url}/app/subscribe/cancel"
    pending_url = f"{base_url}/app/subscribe/pending"

    try:
        from app.services.mercadopago_service import create_preference

        preference = create_preference(user, success_url, failure_url, pending_url)
        db.commit()

        # Redirigir al checkout de Mercado Pago
        checkout_url = preference.get("init_point")
        if not checkout_url:
            # Sandbox si no hay init_point
            checkout_url = preference.get("sandbox_init_point", "")
        if not checkout_url:
            raise RuntimeError("No se pudo obtener la URL de checkout.")

        return RedirectResponse(checkout_url, status_code=303)
    except Exception as e:
        logger.error("Error creando preferencia de Mercado Pago: %s", e)
        raise HTTPException(500, "Error al crear la sesion de pago.")


# ============ Exito / Cancelacion / Pendiente ============

@router.get("/app/subscribe/success", response_class=HTMLResponse)
def subscribe_success(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Pagina mostrada despues de un checkout exitoso.

    Mercado Pago redirige aqui con parametros en la URL.
    El webhook se encarga de activar la suscripcion; esta pagina solo muestra confirmacion.
    """
    return templates.TemplateResponse(
        "pricing.html",
        {
            "request": request,
            "user": user,
            "plan": user.plan,
            "used": user.pdf_count_month,
            "free_limit": FREE_PDF_LIMIT,
            "success": True,
            "mp_public_key": settings.mp_public_key,
        },
    )


@router.get("/app/subscribe/cancel", response_class=HTMLResponse)
def subscribe_cancel(
    request: Request,
    user: User = Depends(require_user),
):
    """Pagina mostrada si el usuario cancela el checkout."""
    return templates.TemplateResponse(
        "pricing.html",
        {
            "request": request,
            "user": user,
            "plan": user.plan,
            "used": user.pdf_count_month,
            "free_limit": FREE_PDF_LIMIT,
            "cancelled": True,
            "mp_public_key": settings.mp_public_key,
        },
    )


@router.get("/app/subscribe/pending", response_class=HTMLResponse)
def subscribe_pending(
    request: Request,
    user: User = Depends(require_user),
):
    """Pagina mostrada si el pago queda pendiente."""
    return templates.TemplateResponse(
        "pricing.html",
        {
            "request": request,
            "user": user,
            "plan": user.plan,
            "used": user.pdf_count_month,
            "free_limit": FREE_PDF_LIMIT,
            "pending": True,
            "mp_public_key": settings.mp_public_key,
        },
    )


# ============ Portal de suscripcion ============

@router.get("/app/subscribe/portal")
def subscription_portal(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Muestra opciones de gestion de suscripcion (cancelar, etc.)."""
    if user.plan != "pro":
        return RedirectResponse("/app/pricing", status_code=303)

    return templates.TemplateResponse(
        "pricing.html",
        {
            "request": request,
            "user": user,
            "plan": user.plan,
            "used": user.pdf_count_month,
            "free_limit": FREE_PDF_LIMIT,
            "show_portal": True,
            "mp_public_key": settings.mp_public_key,
        },
    )


@router.post("/app/subscribe/cancel-subscription")
def cancel_subscription(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Cancela la suscripcion activa del usuario."""
    if user.plan != "pro" or not user.mp_preapproval_id:
        return RedirectResponse("/app/pricing", status_code=303)

    try:
        from app.services.mercadopago_service import cancel_preapproval

        cancel_preapproval(user.mp_preapproval_id)
        user.plan = "free"
        user.subscription_status = "canceled"
        user.mp_preapproval_id = None
        db.commit()
        logger.info("Suscripcion cancelada para %s.", user.username)
    except Exception as e:
        logger.error("Error cancelando suscripcion: %s", e)

    return RedirectResponse("/app/pricing", status_code=303)


# ============ Webhook de Mercado Pago ============

@router.post("/webhook/mercadopago")
async def mercadopago_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    """Procesa eventos de webhook de Mercado Pago (IPN).

    Este endpoint NO debe estar protegido por autenticacion de usuario.
    Mercado Pago envia notificaciones de pago y suscripcion.
    """
    body = await request.body()

    # Mercado Pago envia el tipo de notificacion en query params o body
    query_params = dict(request.query_params)
    body_json = {}
    try:
        body_json = await request.json()
    except Exception:
        pass

    topic = query_params.get("type") or body_json.get("type") or ""
    data_id = query_params.get("data.id") or body_json.get("data", {}).get("id") or ""

    logger.info("Mercado Pago webhook recibido: topic=%s, data_id=%s", topic, data_id)

    try:
        if topic == "payment":
            _handle_payment(data_id, db)
        elif topic in ("subscription_preapproval", "subscription_authorized_payment"):
            _handle_subscription(data_id, db)
        elif topic == "merchant_order":
            # Merchant order - opcional, se puede ignorar
            pass
        else:
            # Intentar detectar por el body
            action = body_json.get("action", "")
            if "payment" in action:
                _handle_payment(data_id, db)
            elif "subscription" in action or "preapproval" in action:
                _handle_subscription(data_id, db)
    except Exception as e:
        logger.error("Error procesando webhook de Mercado Pago: %s", e)

    return {"status": "ok"}


def _handle_payment(payment_id: str, db: Session) -> None:
    """Procesa una notificacion de pago."""
    if not payment_id:
        return

    from app.services.mercadopago_service import get_payment_info

    try:
        payment = get_payment_info(payment_id)
    except Exception as e:
        logger.error("Error obteniendo info de pago %s: %s", payment_id, e)
        return

    status = payment.get("status", "")
    external_ref = payment.get("external_reference", "")

    logger.info("Pago %s: status=%s, external_ref=%s", payment_id, status, external_ref)

    if status == "approved" and external_ref:
        user = db.get(User, external_ref)
        if user:
            user.plan = "pro"
            user.subscription_status = "active"
            db.commit()
            logger.info("Usuario %s activado como Pro via pago %s.", user.username, payment_id)


def _handle_subscription(preapproval_id: str, db: Session) -> None:
    """Procesa una notificacion de suscripcion (preapproval)."""
    if not preapproval_id:
        return

    from app.services.mercadopago_service import get_preapproval_info

    try:
        preapproval = get_preapproval_info(preapproval_id)
    except Exception as e:
        logger.error("Error obteniendo info de preapproval %s: %s", preapproval_id, e)
        return

    status = preapproval.get("status", "")
    external_ref = preapproval.get("external_reference", "")

    logger.info("Preapproval %s: status=%s, external_ref=%s", preapproval_id, status, external_ref)

    if not external_ref:
        return

    user = db.get(User, external_ref)
    if not user:
        logger.warning("Usuario %s no encontrado para preapproval %s", external_ref, preapproval_id)
        return

    if status == "authorized":
        user.plan = "pro"
        user.subscription_status = "active"
        user.mp_preapproval_id = preapproval_id
    elif status in ("cancelled", "paused", "expired"):
        user.plan = "free"
        user.subscription_status = status
        user.mp_preapproval_id = None
    elif status == "pending":
        user.subscription_status = "pending"
        user.mp_preapproval_id = preapproval_id

    db.commit()
    logger.info("Suscripcion actualizada para %s: %s", user.username, status)
