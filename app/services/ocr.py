"""OCR de PDFs con Tesseract (vía PyMuPDF para rasterizar).

Detecta automáticamente el ejecutable de Tesseract en Windows si no está en PATH.
Soporta tanto rutas de archivo como bytes directos (para R2).
"""
from __future__ import annotations

import io
from pathlib import Path

import fitz  # PyMuPDF
import pytesseract
from PIL import Image

from app.config import settings

# Configurar el ejecutable de Tesseract si está seteado o si no está en PATH.
_configured = False


def _ensure_tesseract() -> None:
    global _configured
    if _configured:
        return
    if settings.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd
    else:
        # En Windows, si tesseract no está en PATH, probar la ruta estándar.
        try:
            import shutil

            if shutil.which("tesseract") is None:
                default = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
                if Path(default).exists():
                    pytesseract.pytesseract.tesseract_cmd = default
        except Exception:
            pass
    _configured = True


def ocr_pdf(path_or_bytes: Path | str | bytes, languages: str | None = None, dpi: int | None = None) -> list[str]:
    """Devuelve una lista con el texto OCR por página.

    Args:
        path_or_bytes: ruta al PDF o bytes del contenido del PDF.
    """
    _ensure_tesseract()
    langs = languages or settings.ocr_languages
    dpi = dpi or settings.ocr_dpi

    is_bytes = isinstance(path_or_bytes, bytes)
    if is_bytes:
        doc = fitz.open(stream=path_or_bytes, filetype="pdf")
    else:
        doc = fitz.open(str(path_or_bytes))

    zoom = dpi / 72
    matrix = fitz.Matrix(zoom, zoom)

    pages_text: list[str] = []
    try:
        for page in doc:
            pix = page.get_pixmap(matrix=matrix)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            try:
                text = pytesseract.image_to_string(img, lang=langs)
            except Exception:
                # Si los lenguajes pedidos no existen, intentar solo con eng.
                text = pytesseract.image_to_string(img, lang="eng")
            pages_text.append(text.strip())
    finally:
        doc.close()

    return pages_text


def ocr_image(image_bytes: bytes, languages: str | None = None) -> str:
    """OCR directo sobre bytes de una imagen."""
    _ensure_tesseract()

    langs = languages or settings.ocr_languages
    img = Image.open(io.BytesIO(image_bytes))
    try:
        return pytesseract.image_to_string(img, lang=langs).strip()
    except Exception:
        return pytesseract.image_to_string(img, lang="eng").strip()
