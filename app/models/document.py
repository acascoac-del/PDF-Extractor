"""Modelo de documento (PDF subido) y su estado de procesamiento."""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _uuid_str() -> str:
    return str(uuid.uuid4())


class DocType(str, enum.Enum):
    """Tipos de documento reconocidos."""

    INVOICE = "invoice"          # Factura (prioridad: AFIP A/B/C)
    RECEIPT = "receipt"          # Remito
    QUOTE = "quote"              # Presupuesto
    CONTRACT = "contract"        # Contrato / texto plano
    REPORT = "report"            # Informe
    TABLE = "table"              # Tabla genérica
    GENERIC = "generic"          # Fallback


class DocStatus(str, enum.Enum):
    """Estados del pipeline."""

    UPLOADED = "uploaded"        # Recién subido, sin clasificar
    CLASSIFIED = "classified"    # Clasificado, esperando confirmación del usuario
    QUEUED = "queued"            # Enviado a la cola
    PROCESSING = "processing"    # Worker procesando
    EXTRACTED = "extracted"      # Extracción OK, esperando revisión
    COMPLETED = "completed"      # Revisado / exportado
    FAILED = "failed"            # Error


class Document(Base):
    """PDF subido por un usuario."""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), default="application/pdf")
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_scanned: Mapped[bool | None] = mapped_column(nullable=True)  # None = sin analizar aún

    # Rutas relativas a STORAGE_DIR (uploads/abc.pdf)
    upload_path: Mapped[str] = mapped_column(String(512), nullable=False)

    # Clasificación
    doc_type: Mapped[DocType | None] = mapped_column(Enum(DocType), nullable=True, index=True)
    doc_type_confidence: Mapped[float | None] = mapped_column(nullable=True)
    doc_type_source: Mapped[str | None] = mapped_column(String(32), nullable=True)  # rules|llm|user
    needs_ocr: Mapped[bool] = mapped_column(default=False, nullable=False)

    status: Mapped[DocStatus] = mapped_column(
        Enum(DocStatus), default=DocStatus.UPLOADED, nullable=False, index=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Para Celery
    celery_task_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship("User")  # noqa: F821
    extraction: Mapped["Extraction | None"] = relationship(  # noqa: F821
        "Extraction", back_populates="document", uselist=False, cascade="all, delete-orphan"
    )
    corrections: Mapped[list["Correction"]] = relationship(  # noqa: F821
        "Correction", back_populates="document", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Document {self.original_filename} [{self.status.value}]>"
