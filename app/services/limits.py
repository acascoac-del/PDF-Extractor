"""Limites de uso por plan (freemium).

Planes:
  - Trial (primer mes): 100 PDFs/mes
  - Free (meses siguientes): 3 PDFs/mes
  - Pro: ilimitado
"""
from __future__ import annotations

from datetime import datetime, timezone

TRIAL_PDF_LIMIT = 100
FREE_PDF_LIMIT = 3


def check_pdf_limit(user) -> tuple[bool, int, int]:
    """Verifica si el usuario puede procesar otro PDF.

    Devuelve (puede_procesar, usados, limite).
    Resetea el contador si cambio el mes.
    Admin siempre tiene acceso ilimitado.

    Lógica:
      - Admin → ilimitado
      - Pro → ilimitado
      - Primer mes (trial) → 100 PDFs
      - Meses siguientes (free) → 3 PDFs
    """
    # Admin siempre ilimitado
    from app.models.user import Role
    if user.role == Role.ADMIN:
        return True, 0, -1

    now = datetime.now(timezone.utc)

    # Resetear contador si cambio el mes
    if (
        user.pdf_count_reset_at is None
        or user.pdf_count_reset_at.month != now.month
        or user.pdf_count_reset_at.year != now.year
    ):
        user.pdf_count_month = 0
        user.pdf_count_reset_at = now

    # Pro → ilimitado
    if user.plan == "pro":
        return True, user.pdf_count_month, -1

    # Determinar si es trial (primer mes) o free
    limit = _get_limit_for_user(user)

    return user.pdf_count_month < limit, user.pdf_count_month, limit


def _get_limit_for_user(user) -> int:
    """Devuelve el límite mensual según si es trial o free.

    Trial (100 PDFs): usuario creado este mes (primer mes).
    Free (3 PDFs): usuario con más de un mes de antigüedad.
    """
    now = datetime.now(timezone.utc)
    created = user.created_at

    # Si no tiene fecha de creación, asumir free
    if created is None:
        return FREE_PDF_LIMIT

    # Si el usuario fue creado este mes → trial (primer mes)
    if created.year == now.year and created.month == now.month:
        return TRIAL_PDF_LIMIT

    # Meses siguientes → free
    return FREE_PDF_LIMIT


def increment_pdf_count(user, db) -> None:
    """Incrementa el contador de PDFs procesados en el mes."""
    user.pdf_count_month += 1
    db.commit()
