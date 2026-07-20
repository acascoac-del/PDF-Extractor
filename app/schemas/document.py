"""Esquemas de documentos y extracción."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class UploadResult(BaseModel):
    id: str
    filename: str
    size_bytes: int
    status: str
    message: str = ""


class DocumentTypeOut(BaseModel):
    """Resultado de clasificación (para UI de confirmación)."""

    doc_type: str
    confidence: float
    source: str  # rules | llm | user
    needs_ocr: bool


class FieldOut(BaseModel):
    """Un campo individual extraído."""

    value: Any = None
    source: str = "rules"      # rules | llm | ocr | table | user
    confidence: float = 0.0    # 0.0 - 1.0
    raw: Any = None            # valor crudo antes de normalizar


class ExtractionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str
    doc_type: str
    data: dict[str, Any]
    overall_confidence: float
    llm_model: str | None = None
    updated_at: datetime


class DocumentOut(BaseModel):
    """Documento completo (detalle)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    original_filename: str
    size_bytes: int
    page_count: int | None
    is_scanned: bool | None
    doc_type: str | None
    doc_type_confidence: float | None
    doc_type_source: str | None
    needs_ocr: bool
    status: str
    error_message: str | None = None
    created_at: datetime
    processed_at: datetime | None = None


class DocumentSummary(BaseModel):
    """Fila en el listado / historial."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    original_filename: str
    doc_type: str | None
    status: str
    size_bytes: int
    created_at: datetime
    overall_confidence: float | None = None


class CorrectionIn(BaseModel):
    """Corrección manual enviada desde la UI."""

    field_key: str = Field(min_length=1, max_length=128)
    corrected_value: str | None = None
