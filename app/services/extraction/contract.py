"""Extractor de contratos / texto plano → estructura para Word."""
from __future__ import annotations

from app.services.extraction.base import ExtractionResult
from app.services.pdf_text import PdfContent


def extract_contract(content: PdfContent) -> ExtractionResult:
    result = ExtractionResult()

    # El texto completo por páginas es suficiente para generar el Word.
    result.set_field("title", _extract_title(content.full_text), source="rules", confidence=0.50)
    result.set_field("page_count", content.page_count, source="rules", confidence=1.0)
    result.set_meta("full_text", content.full_text)
    result.set_meta("pages_text", content.pages_text)
    result.set_meta("is_scanned", content.is_scanned)

    return result


def _extract_title(text: str) -> str | None:
    """Intenta sacar el título de las primeras líneas."""
    for line in text.split("\n")[:10]:
        line = line.strip()
        if 4 < len(line) < 120 and not any(
            k in line.lower()
            for k in ["cuit", "domicilio", "tel", "email", "cp", "fecha"]
        ):
            return line
    return None
