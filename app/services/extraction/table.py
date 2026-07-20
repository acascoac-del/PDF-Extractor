"""Extractor de tablas genéricas.

Reconstruye filas/columnas reales desde las tablas detectadas por pdfplumber.
"""
from __future__ import annotations

from app.services.extraction.base import ExtractionResult
from app.services.pdf_text import PdfContent


def extract_table(content: PdfContent) -> ExtractionResult:
    result = ExtractionResult()
    all_tables: list[list[list[str]]] = []
    for page_tables in content.tables:
        for tbl in page_tables:
            all_tables.append(tbl)

    result.set_field("table_count", len(all_tables), source="table", confidence=1.0)
    result.set_meta("page_count", content.page_count)

    # Guardar todas las tablas como items
    for i, tbl in enumerate(all_tables):
        rows = []
        for row in tbl:
            rows.append([cell.strip() if cell else "" for cell in row])
        result.data.setdefault("tables", []).append(
            {"index": i, "rows": rows, "row_count": len(tbl)}
        )

    result.set_meta("is_scanned", content.is_scanned)
    return result
