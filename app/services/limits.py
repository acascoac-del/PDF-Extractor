"""Limites de uso por plan (freemium)."""
from __future__ import annotations

from datetime import datetime, timezone

FREE_PDF_LIMIT = 3


def check_pdf_limit(user) -> tuple[bool, int, int]:
    """Verifica si el usuario puede procesar otro PDF.

    Devuelve (puede_procesar, usados, limite).
    Resetea el contador si cambio el mes.
    Admin siempre tiene acceso ilimitado.
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

    if user.plan == "pro":
        return True, user.pdf_count_month, -1  # ilimitado

    return user.pdf_count_month < FREE_PDF_LIMIT, user.pdf_count_month, FREE_PDF_LIMIT


def increment_pdf_count(user, db) -> None:
    """Incrementa el contador de PDFs procesados en el mes."""
    user.pdf_count_month += 1
    db.commit()
