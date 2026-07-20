"""Extractor genérico (fallback)."""
from __future__ import annotations

from app.services.extraction.base import ExtractionResult
from app.services.pdf_text import PdfContent


def extract_generic(content: PdfContent) -> ExtractionResult:
    result = ExtractionResult()
    result.set_field("page_count", content.page_count, source="rules", confidence=1.0)
    result.set_field("char_count", content.char_count, source="rules", confidence=1.0)
    result.set_meta("full_text", content.full_text)
    result.set_meta("is_scanned", content.is_scanned)
    return result
