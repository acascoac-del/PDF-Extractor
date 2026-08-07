"""Modelo de reglas aprendidas por emisor (CUIT / Razón Social).

Permite que cuando un LLM o usuario procesa una factura por primera vez,
se cree automáticamente una regla reusable para procesar facturas futuras
del mismo emisor sin requerir llamadas al LLM.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _uuid_str() -> str:
    return str(uuid.uuid4())


class EmitterRule(Base):
    """Regla de extracción aprendida para un emisor (CUIT)."""

    __tablename__ = "emitter_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )

    emitter_cuit: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    emitter_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Configuración de extracción aprendida (JSON)
    rule_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    use_count: Mapped[int] = mapped_column(default=1, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<EmitterRule {self.emitter_cuit} ({self.emitter_name})>"
