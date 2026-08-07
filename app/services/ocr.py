"""OCR de PDFs con fallback automático.

Pipeline:
  1. Intentar Tesseract (local, rápido).
  2. Si no está disponible → usar OpenAI Vision API (cloud, gratis con API key).
  3. Si tampoco → devolver texto vacío (el PDF se procesa sin OCR).

Soporta tanto rutas de archivo como bytes directos (para R2).
"""
from __future__ import annotations

import io
import base64
import logging
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image

from app.config import settings

logger = logging.getLogger(__name__)

# Configurar el ejecutable de Tesseract si está seteado o si no está en PATH.
_tesseract_configured = False
_tesseract_available = None


def _ensure_tesseract() -> bool:
    """Configura Tesseract y devuelve True si está disponible."""
    global _tesseract_configured, _tesseract_available
    if _tesseract_configured:
        return _tesseract_available is True

    _tesseract_configured = True
    try:
        import pytesseract
    except ImportError:
        _tesseract_available = False
        return False

    if settings.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd
    else:
        try:
            import shutil
            if shutil.which("tesseract") is None:
                default = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
                if Path(default).exists():
                    pytesseract.pytesseract.tesseract_cmd = default
                else:
                    _tesseract_available = False
                    return False
        except Exception:
            _tesseract_available = False
            return False

    _tesseract_available = True
    return True


def _render_page_png(page, dpi: int = 150) -> bytes:
    """Renderiza una página de PyMuPDF como PNG bytes."""
    zoom = dpi / 72
    matrix = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=matrix)
    return pix.tobytes("png")


def _ocr_with_openai_vision(image_bytes: bytes) -> str:
    """OCR usando OpenAI Vision API (gpt-4o-mini). Gratis con tu API key existente."""
    if not settings.openai_api_key:
        return ""

    try:
        from openai import OpenAI
        client = OpenAI(
            base_url=settings.openai_base_url,
            api_key=settings.openai_api_key,
            timeout=30,
        )

        b64_img = base64.b64encode(image_bytes).decode("utf-8")

        resp = client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Extraé TODO el texto visible de esta imagen de una página de PDF. "
                                "Devolvé ÚNICAMENTE el texto extraído, sin explicaciones ni formato adicional. "
                                "Mantené la estructura original (saltos de línea, tabulaciones, etc.)."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{b64_img}",
                                "detail": "low",
                            },
                        },
                    ],
                }
            ],
            max_tokens=4096,
            temperature=0.0,
        )

        text = resp.choices[0].message.content or ""
        return text.strip()
    except Exception as e:
        logger.warning("OpenAI Vision OCR failed: %s", e)
        return ""


def _ocr_page_tesseract(image_bytes: bytes, langs: str) -> str:
    """OCR con Tesseract (local)."""
    try:
        import pytesseract
        img = Image.open(io.BytesIO(image_bytes))
        return pytesseract.image_to_string(img, lang=langs).strip()
    except Exception:
        try:
            import pytesseract
            img = Image.open(io.BytesIO(image_bytes))
            return pytesseract.image_to_string(img, lang="eng").strip()
        except Exception as e:
            logger.warning("Tesseract OCR failed: %s", e)
            return ""


def ocr_pdf(path_or_bytes: Path | str | bytes, languages: str | None = None, dpi: int | None = None) -> list[str]:
    """Devuelve una lista con el texto OCR por página.

    Pipeline de fallback:
      1. Tesseract (local, rápido, gratis)
      2. OpenAI Vision (cloud, gratis con API key)

    Args:
        path_or_bytes: ruta al PDF o bytes del contenido del PDF.
    """
    langs = languages or settings.ocr_languages
    dpi = dpi or settings.ocr_dpi

    # Reducir DPI en Vercel para ser más rápido (150 es suficiente para OCR)
    if settings.environment == "production":
        dpi = min(dpi, 150)

    is_bytes = isinstance(path_or_bytes, bytes)
    if is_bytes:
        doc = fitz.open(stream=path_or_bytes, filetype="pdf")
    else:
        doc = fitz.open(str(path_or_bytes))

    has_tesseract = _ensure_tesseract()
    has_openai = bool(settings.openai_api_key)

    pages_text: list[str] = []
    try:
        for page in doc:
            img_bytes = _render_page_png(page, dpi)
            text = ""

            # 1. Intentar Tesseract (local)
            if has_tesseract:
                text = _ocr_page_tesseract(img_bytes, langs)

            # 2. Fallback: OpenAI Vision (cloud)
            if not text and has_openai:
                text = _ocr_with_openai_vision(img_bytes)

            pages_text.append(text)
    finally:
        doc.close()

    return pages_text


def ocr_image(image_bytes: bytes, languages: str | None = None) -> str:
    """OCR directo sobre bytes de imagen con fallback automático."""
    langs = languages or settings.ocr_languages

    # 1. Tesseract
    if _ensure_tesseract():
        text = _ocr_page_tesseract(image_bytes, langs)
        if text:
            return text

    # 2. OpenAI Vision
    if settings.openai_api_key:
        return _ocr_with_openai_vision(image_bytes)

    return ""
