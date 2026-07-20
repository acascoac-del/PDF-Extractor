"""Modelo de corrección manual del usuario (feedback loop).

Cada corrección guarda: campo corregido, valor original, valor final, y un
contexto (hash del documento / proveedor) para sugerir correcciones similares
en futuras extracciones.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _uuid_str() -> str:
    return str(uuid.uuid4())


class Correction(Base):
    """Una corrección manual sobre un campo extraído."""

    __tablename__ = "corrections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    field_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    original_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrected_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Contexto para feedback: proveedor/razón social detectada (si aplica)
    context_hint: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    document: Mapped["Document"] = relationship("Document", back_populates="corrections")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Correction {self.field_key}={self.corrected_value!r}>"
