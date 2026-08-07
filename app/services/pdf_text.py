"""Extracción de texto de PDFs (nativos y escaneados).

Pipeline optimizado para Vercel (timeout 10s):
  1. PyMuPDF como extractor primario (3-5x más rápido que pdfplumber).
  2. pdfplumber solo para extracción de tablas (si es necesario).
  3. Si hay poco texto por página → asumir escaneado y pasar OCR.
  4. OCR con fallback: Tesseract (local) → OpenAI Vision (cloud).

Soporta tanto rutas de archivo como bytes directos (para R2).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # PyMuPDF

from app.config import settings

logger = logging.getLogger(__name__)

# Umbral: si una página tiene menos de N caracteres "significativos", la
# consideramos escaneada y necesita OCR.
_MIN_CHARS_PER_PAGE = 30

# Flag: intentar pdfplumber para tablas (puede ser lento en PDFs grandes)
_TABLES_ENABLED = True

# Timeout para extracción de tablas con pdfplumber (en segundos)
_TABLES_TIMEOUT = 5


import re


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

    def get_unique_pages(self) -> list[tuple[int, str]]:
        """Devuelve las páginas únicas del documento [(index, text), ...], omitiendo copias DUPLICADO/TRIPLICADO.

        Considera tanto el texto como el contenido de tablas para determinar unicidad.
        """
        if not self.pages_text:
            if self.tables:
                return [(i, self.pages_text[i] if i < len(self.pages_text) else "") for i in range(len(self.tables))]
            if self.full_text:
                return [(0, self.full_text)]
            return []

        unique_pages: list[tuple[int, str]] = []
        seen_exact_texts: set[str] = set()

        for idx, text in enumerate(self.pages_text):
            text_str = text or ""
            text_upper = text_str.upper()

            sheet_match = re.search(r"(?:HOJA|P[ÁA]GINA|PAG\.?)\s*(\d+)\s*(?:DE|/)\s*(\d+)", text_upper)
            current_sheet = int(sheet_match.group(1)) if sheet_match else None

            # Texto de comparación ignorando etiquetas de copia
            cleaned_text = re.sub(
                r"\b(ORIGINAL|DUPLICADO|TRIPLICADO|CUATRIPLICADO|COPIA|EMISOR|CLIENTE|CONTABILIDAD|EJEMPLAR)\b",
                "",
                text_upper,
            )
            normalized_text = re.sub(r"\s+", " ", cleaned_text).strip()

            # Incluir contenido de tablas en la normalización para detectar páginas con misma cabecera
            # pero diferentes datos tabulares (ej. anexos multi-página)
            table_content = ""
            if idx < len(self.tables) and self.tables[idx]:
                for tbl in self.tables[idx]:
                    for row in tbl:
                        table_content += " " + " ".join(str(c or "") for c in row)
            table_normalized = re.sub(r"\s+", " ", table_content.upper()).strip()

            # Combinar texto y tablas para la clave de unicidad
            combined_key = normalized_text + "|" + table_normalized

            # 1. Si la combinación texto+tablas ya fue procesada, es una copia
            if combined_key and combined_key in seen_exact_texts:
                continue

            # 2. Si tiene etiqueta explícita de copia (DUPLICADO/TRIPLICADO) y coincide la hoja
            is_copy_label = any(
                tag in text_upper
                for tag in ["DUPLICADO", "TRIPLICADO", "CUATRIPLICADO", "COPIA EMISOR", "COPIA CONTABILIDAD", "COPIA - CLIENTE"]
            )

            if is_copy_label and current_sheet is not None:
                already_processed = False
                for prev_idx, prev_text in unique_pages:
                    prev_match = re.search(r"(?:HOJA|P[ÁA]GINA|PAG\.?)\s*(\d+)\s*(?:DE|/)\s*(\d+)", prev_text.upper())
                    if prev_match and int(prev_match.group(1)) == current_sheet:
                        already_processed = True
                        break
                if already_processed:
                    continue

            if combined_key:
                seen_exact_texts.add(combined_key)
            unique_pages.append((idx, text_str))

        return unique_pages if unique_pages else [(i, t) for i, t in enumerate(self.pages_text)]

    @property
    def unique_text(self) -> str:
        """Devuelve el texto concatenado únicamente de las páginas no duplicadas."""
        unique = self.get_unique_pages()
        return "\n\n".join(t for _, t in unique)


def extract_text(path_or_bytes: Path | str | bytes, force_ocr: bool = False) -> PdfContent:
    """Extrae texto de un PDF.

    Pipeline optimizado para Vercel:
      1. PyMuPDF como extractor primario (texto nativo, rápido).
      2. pdfplumber solo para tablas (con timeout).
      3. OCR si el PDF es escaneado (Tesseract → OpenAI Vision).

    Args:
        path_or_bytes: ruta al PDF o bytes del contenido del PDF.
        force_ocr: ignorar texto nativo y forzar OCR.
    """
    is_bytes = isinstance(path_or_bytes, bytes)
    if not is_bytes:
        path = Path(path_or_bytes)
        if not path.exists():
            raise FileNotFoundError(path)

    content = PdfContent()

    # ---- 1. PyMuPDF como extractor primario (rápido) ----
    if not force_ocr:
        try:
            if is_bytes:
                doc = fitz.open(stream=path_or_bytes, filetype="pdf")
            else:
                doc = fitz.open(str(path_or_bytes))

            content.page_count = doc.page_count
            for page in doc:
                text = page.get_text("text") or ""
                content.pages_text.append(text.strip())
            doc.close()
        except Exception as e:
            logger.warning("PyMuPDF extraction failed: %s", e)
            content.pages_text = []
            content.page_count = 0

    # ---- 2. Fallback: page_count con PyMuPDF si no se obtuvo ----
    if content.page_count == 0:
        try:
            if is_bytes:
                doc = fitz.open(stream=path_or_bytes, filetype="pdf")
            else:
                doc = fitz.open(str(path_or_bytes))
            content.page_count = doc.page_count
            doc.close()
        except Exception:
            pass

    # ---- 3. Extraer tablas con pdfplumber (con timeout implícito) ----
    if _TABLES_ENABLED and not force_ocr and content.page_count > 0:
        try:
            _extract_tables_pdfplumber(path_or_bytes, is_bytes, content)
        except Exception as e:
            logger.warning("pdfplumber table extraction failed (continuing without tables): %s", e)
            content.tables = [[] for _ in range(content.page_count)]

    # Asegurar que tables tenga la misma cantidad de entries que pages_text
    while len(content.tables) < len(content.pages_text):
        content.tables.append([])

    content.full_text = "\n\n".join(content.pages_text)

    # ---- 4. Decidir si necesita OCR ----
    if content.page_count > 0:
        avg_chars = content.char_count / content.page_count
        content.is_scanned = avg_chars < _MIN_CHARS_PER_PAGE

    # ---- 5. OCR si corresponde (Tesseract → OpenAI Vision) ----
    if content.is_scanned or force_ocr:
        try:
            from app.services.ocr import ocr_pdf

            ocr_pages = ocr_pdf(path_or_bytes)
            # Mezclar: si ya había algo de texto nativo, lo dejamos pero agregamos OCR.
            if content.pages_text and not force_ocr:
                content.pages_text = [
                    (nt + "\n" + ot).strip() if (ot := ocr_pages[i]) else nt
                    for i, nt in enumerate(content.pages_text)
                ]
            else:
                content.pages_text = ocr_pages
            content.full_text = "\n\n".join(content.pages_text)
        except Exception as e:
            logger.warning("OCR failed (continuing without OCR): %s", e)

    return content


def _extract_tables_pdfplumber(path_or_bytes, is_bytes: bool, content: PdfContent) -> None:
    """Extrae tablas con pdfplumber. Se ejecuta con timeout implícito."""
    import pdfplumber

    if is_bytes:
        import io
        pdf_file = io.BytesIO(path_or_bytes)
        pdf = pdfplumber.open(pdf_file)
    else:
        pdf = pdfplumber.open(str(path_or_bytes))

    with pdf:
        for page in pdf.pages:
            try:
                tables = page.extract_tables() or []
                content.tables.append(
                    [[[(c or "") for c in row] for row in tbl] for tbl in tables]
                )
            except Exception:
                content.tables.append([])


def render_page_image(path_or_bytes: Path | str | bytes, page_number: int, dpi: int | None = None) -> bytes:
    """Renderiza una página como PNG (para preview o visor)."""
    dpi = dpi or settings.ocr_dpi
    is_bytes = isinstance(path_or_bytes, bytes)
    if is_bytes:
        doc = fitz.open(stream=path_or_bytes, filetype="pdf")
    else:
        doc = fitz.open(str(path_or_bytes))
    try:
        page = doc[page_number]
        zoom = dpi / 72
        matrix = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=matrix)
        return pix.tobytes("png")
    finally:
        doc.close()
