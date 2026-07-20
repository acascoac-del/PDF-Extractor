"""Servicio de integracion con Stripe.

Maneja Checkout Sessions, Customer Portal y webhooks.
"""
from __future__ import annotations

import logging

import stripe

from app.config import settings

logger = logging.getLogger(__name__)

# Configurar la API key de Stripe al importar el modulo
if settings.stripe_secret_key:
    stripe.api_key = settings.stripe_secret_key

PRO_PRICE_ID = settings.stripe_price_id  # price_xxx del dashboard de Stripe


def create_checkout_session(user, success_url: str, cancel_url: str):
    """Crea una Stripe Checkout Session para el plan Pro ($5/mes).

    Si el usuario no tiene un customer en Stripe, lo crea.
    """
    if not settings.stripe_secret_key:
        raise RuntimeError("STRIPE_SECRET_KEY no configurada.")

    # Crear o recuperar customer
    if not user.stripe_customer_id:
        customer = stripe.Customer.create(
            email=user.email,
            name=user.full_name or user.username,
            metadata={"user_id": user.id},
        )
        user.stripe_customer_id = customer.id

    session = stripe.checkout.Session.create(
        customer=user.stripe_customer_id,
        mode="subscription",
        line_items=[{"price": PRO_PRICE_ID, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"user_id": user.id},
    )
    return session


def create_portal_session(user, return_url: str):
    """Crea una sesion del Stripe Customer Portal para gestionar la suscripcion."""
    if not user.stripe_customer_id:
        raise ValueError("El usuario no tiene un customer en Stripe.")

    session = stripe.billing_portal.Session.create(
        customer=user.stripe_customer_id,
        return_url=return_url,
    )
    return session


def handle_webhook(payload: bytes, sig_header: str):
    """Procesa un evento de webhook de Stripe.

    Lanza stripe.error.SignatureVerificationError si la firma no coincide.
    """
    event = stripe.Webhook.construct_event(
        payload, sig_header, settings.stripe_webhook_secret
    )
    return event
