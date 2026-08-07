"""Integracion REST con PayPal Subscriptions.

PayPal requiere un producto y un plan creados previamente en el dashboard.
El identificador del plan se configura mediante PAYPAL_PLAN_ID.
"""
from __future__ import annotations

import base64
import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def _credentials() -> tuple[str, str]:
    if not settings.paypal_enabled:
        raise RuntimeError("PayPal no esta configurado.")
    return settings.paypal_client_id, settings.paypal_client_secret


def _access_token() -> str:
    client_id, client_secret = _credentials()
    encoded = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    response = httpx.post(
        f"{settings.paypal_base_url.rstrip('/')}/v1/oauth2/token",
        headers={
            "Accept": "application/json",
            "Accept-Language": "en_US",
            "Authorization": f"Basic {encoded}",
        },
        data={"grant_type": "client_credentials"},
        timeout=20.0,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def _request(method: str, path: str, **kwargs: Any) -> dict:
    token = _access_token()
    headers = kwargs.pop("headers", {})
    headers.update({
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    })
    response = httpx.request(
        method,
        f"{settings.paypal_base_url.rstrip('/')}{path}",
        headers=headers,
        timeout=20.0,
        **kwargs,
    )
    response.raise_for_status()
    return response.json() if response.content else {}


def create_subscription(user, return_url: str, cancel_url: str) -> dict:
    """Crea una suscripcion PayPal y devuelve la respuesta de PayPal."""
    return _request(
        "POST",
        "/v1/billing/subscriptions",
        headers={"Prefer": "return=representation"},
        json={
            "plan_id": settings.paypal_plan_id,
            "custom_id": str(user.id),
            "subscriber": {"email_address": user.email},
            "application_context": {
                "brand_name": settings.app_name,
                "locale": "es-AR",
                "shipping_preference": "NO_SHIPPING",
                "user_action": "SUBSCRIBE_NOW",
                "return_url": return_url,
                "cancel_url": cancel_url,
            },
        },
    )


def get_subscription(subscription_id: str) -> dict:
    """Obtiene el estado actual de una suscripcion PayPal."""
    return _request("GET", f"/v1/billing/subscriptions/{subscription_id}")


def approval_url(subscription: dict) -> str | None:
    """Devuelve el enlace HATEOAS que lleva al usuario a aprobar el pago."""
    for link in subscription.get("links", []):
        if link.get("rel") == "approve":
            return link.get("href")
    return None
