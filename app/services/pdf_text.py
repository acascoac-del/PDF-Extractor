"""Extracción de texto de PDFs (nativos y escaneados).

Pipeline:
  1. Intentar pdfplumber (texto seleccionable).
  2. Si hay poco texto por página → asumir escaneado y pasar OCR.
  3. Devolver: pages_text (lista por página), full_text, page_count, is_scanned.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber
import fitz  # PyMuPDF

from app.config import settings


# Umbral: si una página tiene menos de N caracteres "significativos", la
# consideramos escaneada y necesita OCR.
_MIN_CHARS_PER_PAGE = 30


@dataclass
class PdfContent:
    page_count: int = 0
    is_scanned: bool = False
    pages_text: list[str] = field(default_factory=list)
    full_text: str = ""
    tables: list[list[list[list[str]]]] = field(default_factory=list)  # por página

    @property
    def char_count(self) -> int:
        return sum(len(t) for t in self.pages_text)


def extract_text(path: Path | str, force_ocr: bool = False) -> PdfContent:
    """Extrae texto de un PDF.

    Args:
        path: ruta al PDF.
        force_ocr: ignorar texto nativo y forzar OCR.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)

    content = PdfContent()

    # ---- Texto nativo + tablas con pdfplumber ----
    if not force_ocr:
        try:
            with pdfplumber.open(str(path)) as pdf:
                content.page_count = len(pdf.pages)
                for page in pdf.pages:
                    text = page.extract_text() or ""
                    content.pages_text.append(text)
                    try:
                        content.tables.append(
                            [[[(c or "") for c in row] for row in tbl]
                             for tbl in (page.extract_tables() or [])]
                        )
                    except Exception:
                        content.tables.append([])
        except Exception:
            # Si pdfplumber falla, probamos PyMuPDF como fallback.
            content.pages_text = []
            content.tables = []

    # ---- PyMuPDF como respaldo y para page_count ----
    if content.page_count == 0:
        try:
            doc = fitz.open(str(path))
            content.page_count = doc.page_count
            doc.close()
        except Exception:
            pass

    content.full_text = "\n\n".join(content.pages_text)

    # ---- Decidir si necesita OCR ----
    if content.page_count > 0:
        avg_chars = content.char_count / content.page_count
        content.is_scanned = avg_chars < _MIN_CHARS_PER_PAGE

    # ---- OCR si corresponde ----
    if content.is_scanned or force_ocr:
        from app.services.ocr import ocr_pdf

        ocr_pages = ocr_pdf(path)
        # Mezclar: si ya había algo de texto nativo, lo dejamos pero agregamos OCR.
        if content.pages_text and not force_ocr:
            content.pages_text = [
                (nt + "\n" + ot).strip() if (ot := ocr_pages[i]) else nt
                for i, nt in enumerate(content.pages_text)
            ]
        else:
            content.pages_text = ocr_pages
        content.full_text = "\n\n".join(content.pages_text)

    return content


def render_page_image(path: Path | str, page_number: int, dpi: int | None = None) -> bytes:
    """Renderiza una página como PNG (para preview o visor)."""
    dpi = dpi or settings.ocr_dpi
    doc = fitz.open(str(path))
    try:
        page = doc[page_number]
        zoom = dpi / 72
        matrix = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=matrix)
        return pix.tobytes("png")
    finally:
        doc.close()
