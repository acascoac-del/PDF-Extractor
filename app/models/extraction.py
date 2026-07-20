"""Modelo de extracción: datos estructurados extraídos de un documento.

El campo `data` guarda un JSON con la estructura específica del tipo de documento
(campos de factura, filas de tabla, etc.), junto con metadatos de confianza por campo.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.database import Base


def _uuid_str() -> str:
    return str(uuid.uuid4())


class FieldSource(str, enum.Enum):
    """De dónde proviene un campo extraído (para scoring de confianza)."""

    RULES = "rules"      # Regex / keyword
    LLM = "llm"          # LLM (gpt-4o-mini, etc.)
    OCR = "ocr"          # Vino de OCR
    TABLE = "table"      # Tabla detectada por pdfplumber
    USER = "user"        # Corregido por el usuario (confianza máxima)


class Extraction(Base):
    """Datos extraídos de un documento."""

    __tablename__ = "extractions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )

    doc_type: Mapped[str] = mapped_column(String(32), nullable=False)  # snapshot del tipo

    # Estructura: {"fields": {key: {"value":..., "source":..., "confidence":..., "raw":...}},
    #              "items": [...], "meta": {...}}
    data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    overall_confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    llm_model: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    document: Mapped["Document"] = relationship("Document", back_populates="extraction")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Extraction doc={self.document_id} type={self.doc_type}>"
