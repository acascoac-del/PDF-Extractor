"""Servicio de integración con Mercado Pago.

Maneja preferencias de pago, suscripciones (preapproval) y webhooks.
"""
from __future__ import annotations

import logging

from app.config import settings

logger = logging.getLogger(__name__)

# SDK de Mercado Pago (lazy import para no fallar si no está instalado)
_sdk = None


def _get_sdk():
    global _sdk
    if _sdk is None:
        import mercadopago
        _sdk = mercadopago.SDK(settings.mp_access_token)
    return _sdk


def create_preference(user, success_url: str, failure_url: str, pending_url: str) -> dict:
    """Crea una preferencia de pago para una suscripcion mensual.

    Devuelve la respuesta de Mercado Pago con el init_point (URL de checkout).
    """
    if not settings.mp_access_token:
        raise RuntimeError("MP_ACCESS_TOKEN no configurado.")

    sdk = _get_sdk()
    preference_data = {
        "items": [
            {
                "title": "PDF Extractor Pro - Suscripcion Mensual",
                "quantity": 1,
                "currency_id": "ARS",
                "unit_price": settings.mp_monthly_price,
            }
        ],
        "payer": {
            "email": user.email,
        },
        "back_urls": {
            "success": success_url,
            "failure": failure_url,
            "pending": pending_url,
        },
        "auto_return": "approved",
        "external_reference": str(user.id),
        "notification_url": f"{settings.app_url}/webhook/mercadopago",
    }
    preference = sdk.preference().create(preference_data)
    return preference["response"]


def create_preapproval(user) -> dict:
    """Crea una suscripcion recurrente (preapproval) en Mercado Pago.

    Devuelve la respuesta con el init_point para redirigir al usuario.
    """
    if not settings.mp_access_token:
        raise RuntimeError("MP_ACCESS_TOKEN no configurado.")

    sdk = _get_sdk()
    preapproval_data = {
        "reason": "PDF Extractor Pro",
        "external_reference": str(user.id),
        "payer_email": user.email,
        "auto_recurring": {
            "frequency": 1,
            "frequency_type": "months",
            "transaction_amount": settings.mp_monthly_price,
            "currency_id": "ARS",
        },
        "back_url": f"{settings.app_url}/app/subscribe/success",
        "status": "authorized",
    }
    preapproval = sdk.preapproval().create(preapproval_data)
    return preapproval["response"]


def get_payment_info(payment_id: str) -> dict:
    """Obtiene informacion de un pago de Mercado Pago."""
    sdk = _get_sdk()
    payment = sdk.payment().get(payment_id)
    return payment["response"]


def get_preapproval_info(preapproval_id: str) -> dict:
    """Obtiene informacion de una suscripcion (preapproval)."""
    sdk = _get_sdk()
    preapproval = sdk.preapproval().get(preapproval_id)
    return preapproval["response"]


def cancel_preapproval(preapproval_id: str) -> dict:
    """Cancela una suscripcion (preapproval)."""
    sdk = _get_sdk()
    data = {"status": "cancelled"}
    result = sdk.preapproval().update(preapproval_id, data)
    return result["response"]
