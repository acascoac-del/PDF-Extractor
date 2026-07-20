"""Router de suscripcion: precios, checkout, webhooks, portal de cliente."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import settings
from app.deps import get_db, get_current_user_optional, require_user
from app.models.user import User
from app.services.limits import check_pdf_limit, FREE_PDF_LIMIT
from app.services import stripe_service

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
    stripe_publishable = settings.stripe_publishable_key

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
            "stripe_publishable_key": stripe_publishable,
        },
    )


# ============ Checkout de Stripe ============

@router.post("/app/subscribe")
def subscribe(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Crea una Checkout Session de Stripe y redirige al usuario."""
    if user.plan == "pro":
        return RedirectResponse("/app/pricing", status_code=303)

    success_url = str(request.base_url).rstrip("/") + "/app/subscribe/success?session_id={CHECKOUT_SESSION_ID}"
    cancel_url = str(request.base_url).rstrip("/") + "/app/subscribe/cancel"

    try:
        session = stripe_service.create_checkout_session(user, success_url, cancel_url)
        db.commit()  # guardar posible stripe_customer_id
        return RedirectResponse(session.url, status_code=303)
    except Exception as e:
        logger.error("Error creando checkout session: %s", e)
        raise HTTPException(500, "Error al crear la sesion de pago.")


# ============ Exito / Cancelacion ============

@router.get("/app/subscribe/success", response_class=HTMLResponse)
def subscribe_success(
    request: Request,
    session_id: str = "",
    user: User = Depends(require_user),
):
    """Pagina mostrada despues de un checkout exitoso."""
    return templates.TemplateResponse(
        "pricing.html",
        {
            "request": request,
            "user": user,
            "plan": user.plan,
            "used": user.pdf_count_month,
            "free_limit": FREE_PDF_LIMIT,
            "success": True,
            "stripe_publishable_key": settings.stripe_publishable_key,
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
            "stripe_publishable_key": settings.stripe_publishable_key,
        },
    )


# ============ Portal de cliente ============

@router.get("/app/subscribe/portal")
def customer_portal(
    request: Request,
    user: User = Depends(require_user),
):
    """Redirige al Stripe Customer Portal para gestionar la suscripcion."""
    if not user.stripe_customer_id:
        return RedirectResponse("/app/pricing", status_code=303)

    return_url = str(request.base_url).rstrip("/") + "/app/settings"
    try:
        session = stripe_service.create_portal_session(user, return_url)
        return RedirectResponse(session.url, status_code=303)
    except Exception as e:
        logger.error("Error creando portal session: %s", e)
        raise HTTPException(500, "Error al abrir el portal de suscripcion.")


# ============ Webhook de Stripe ============

@router.post("/webhook/stripe")
async def stripe_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    """Procesa eventos de webhook de Stripe.

    Este endpoint NO debe estar protegido por autenticacion de usuario.
    Stripe envia la firma en el header stripe-signature.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe_service.handle_webhook(payload, sig_header)
    except Exception as e:
        logger.warning("Webhook invalido: %s", e)
        raise HTTPException(400, "Webhook invalido.")

    event_type = event["type"]
    data = event["data"]["object"]
    logger.info("Stripe webhook recibido: %s", event_type)

    if event_type == "checkout.session.completed":
        _handle_checkout_completed(data, db)
    elif event_type == "customer.subscription.updated":
        _handle_subscription_updated(data, db)
    elif event_type == "customer.subscription.deleted":
        _handle_subscription_deleted(data, db)

    return {"status": "ok"}


def _handle_checkout_completed(session: dict, db: Session) -> None:
    """Activa el plan Pro cuando el checkout se completa."""
    user_id = session.get("metadata", {}).get("user_id")
    if not user_id:
        logger.warning("checkout.session.completed sin user_id en metadata")
        return

    user = db.get(User, user_id)
    if not user:
        logger.warning("Usuario %s no encontrado para checkout.session.completed", user_id)
        return

    user.plan = "pro"
    user.subscription_status = "active"
    user.stripe_subscription_id = session.get("subscription")
    db.commit()
    logger.info("Usuario %s activado como Pro.", user.username)


def _handle_subscription_updated(subscription: dict, db: Session) -> None:
    """Actualiza el estado de la suscripcion cuando Stripe envia un update."""
    customer_id = subscription.get("customer")
    if not customer_id:
        return

    user = db.query(User).filter(User.stripe_customer_id == customer_id).first()
    if not user:
        logger.warning("No se encontro usuario con customer_id %s", customer_id)
        return

    status = subscription.get("status", "none")
    user.subscription_status = status

    if status == "active":
        user.plan = "pro"
    elif status in ("past_due", "canceled", "unpaid"):
        user.plan = "free"

    # Guardar fecha de fin si existe
    end_ts = subscription.get("current_period_end")
    if end_ts:
        from datetime import datetime, timezone
        user.subscription_end_date = datetime.fromtimestamp(end_ts, tz=timezone.utc)

    db.commit()
    logger.info("Suscripcion actualizada para %s: %s", user.username, status)


def _handle_subscription_deleted(subscription: dict, db: Session) -> None:
    """Revoca el plan Pro cuando la suscripcion se cancela/elimina."""
    customer_id = subscription.get("customer")
    if not customer_id:
        return

    user = db.query(User).filter(User.stripe_customer_id == customer_id).first()
    if not user:
        logger.warning("No se encontro usuario con customer_id %s", customer_id)
        return

    user.plan = "free"
    user.subscription_status = "canceled"
    db.commit()
    logger.info("Suscripcion cancelada para %s. Plan revertido a free.", user.username)
