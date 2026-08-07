"""Clasificación y pipeline de extracción.

Pipeline optimizado para Vercel (timeout 10s):
  - Extracción rápida con PyMuPDF (primario).
  - Tablas con pdfplumber (fallback, con timeout).
  - OCR con OpenAI Vision (si Tesseract no disponible).
  - Fallback graceful: si falla la extracción completa, devolver parcial.

Adaptado para Vercel: acepta bytes directos (para R2) además de rutas de archivo.
"""
from __future__ import annotations

import logging
import re
import signal
import platform
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.document import DocStatus, DocType, Document
from app.models.extraction import Extraction
from app.services.pdf_text import extract_text

logger = logging.getLogger(__name__)


# Keywords para clasificación rápida (reglas)
_KEYWORDS: dict[DocType, list[str]] = {
    DocType.INVOICE: [
        "factura", "comprobante fiscal", "cae", "cuit", "razón social",
        "condición de iva", "punto de venta", "nro. factura", "n° de factura",
        "codigo autorizacion", "fecha de emision", "subtotal", "total",
        "importe", "gravado", "no gravado", "exento", "neto",
        "telepase", "autopista", "peaje", "transacciones telepase",
    ],
    DocType.RECEIPT: [
        "remito", "remito nro", "destinatario", "remitente",
        "código de transporte",
    ],
    DocType.QUOTE: [
        "presupuesto", "cotización", "validez", "condiciones de pago",
        "vigencia de la oferta",
    ],
    DocType.CONTRACT: [
        "contrato", "convenio", "acuerdo", "cláusula", "partes",
        "testigos", "firma", "domicilio legal", "domicilio constituido",
        "plazo", "rescisión", "jurisdicción",
    ],
    DocType.REPORT: [
        "informe", "reporte", "resumen ejecutivo", "conclusión",
        "recomendación", "hallazgo",
    ],
}


def classify_by_rules(text: str) -> tuple[DocType, float]:
    """Clasifica por conteo de keywords. Devuelve (tipo, confianza)."""
    text_lower = text.lower()
    scores: dict[DocType, int] = {}
    total_matches = 0
    for dt, keywords in _KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in text_lower)
        scores[dt] = count
        total_matches += count

    if total_matches == 0:
        return DocType.GENERIC, 0.1

    best = max(scores, key=scores.get)
    confidence = scores[best] / total_matches
    return best, round(confidence, 2)


def classify_document(doc: Document, full_text: str) -> None:
    """Establece doc_type, confidence y source en el documento."""
    doc_type, confidence = classify_by_rules(full_text)
    doc.doc_type = doc_type
    doc.doc_type_confidence = confidence
    doc.doc_type_source = "rules"
    doc.status = DocStatus.CLASSIFIED


def run_pipeline_sync(doc: Document, pdf_path_or_bytes: Path | str | bytes, db: Session, user=None) -> None:
    """Pipeline síncrono completo: texto → clasificación → extracción.

    Acepta tanto una ruta de archivo como bytes directos del PDF.
    En Vercel se usa con bytes descargados de R2.

    Manejo de timeouts:
      - Si la extracción completa falla por timeout, intenta extracción parcial.
      - Si todo falla, marca el documento como FAILED con mensaje descriptivo.
    """
    import time
    start_time = time.monotonic()

    doc.status = DocStatus.PROCESSING
    db.commit()

    # 1. Extraer texto (soporta bytes o ruta)
    try:
        content = extract_text(pdf_path_or_bytes)
        doc.page_count = content.page_count
        doc.is_scanned = content.is_scanned
        doc.needs_ocr = content.is_scanned
    except Exception as e:
        logger.error("Text extraction failed: %s", e)
        doc.status = DocStatus.FAILED
        doc.error_message = f"Error al extraer texto del PDF: {e}"
        db.commit()
        return

    elapsed = time.monotonic() - start_time
    logger.info("Text extraction took %.1fs (%d pages, %d chars)", elapsed, content.page_count, content.char_count)

    # 2. Clasificar (si no tiene tipo seteado por el usuario)
    if doc.doc_type is None or doc.doc_type_source != "user":
        try:
            classify_document(doc, content.full_text)
        except Exception as e:
            logger.warning("Classification failed, using generic: %s", e)
            doc.doc_type = DocType.GENERIC
            doc.doc_type_source = "fallback"
    db.commit()

    # 3. Extraer datos según tipo
    from app.services.extraction.invoice import extract_invoice
    from app.services.extraction.base import ExtractionResult
    from app.services.confidence import compute_overall_confidence

    result: ExtractionResult | None = None

    try:
        if doc.doc_type == DocType.INVOICE:
            result = extract_invoice(content, user=user)
        elif doc.doc_type == DocType.TABLE:
            from app.services.extraction.table import extract_table
            result = extract_table(content)
        elif doc.doc_type == DocType.CONTRACT:
            from app.services.extraction.contract import extract_contract
            result = extract_contract(content)
        else:
            from app.services.extraction.generic import extract_generic
            result = extract_generic(content, user=user)
    except Exception as e:
        logger.error("Extraction failed: %s", e)
        # Fallback: intentar extracción genérica (solo texto, sin LLM)
        try:
            from app.services.extraction.generic import extract_generic
            result = extract_generic(content, user=None)
            if result:
                result.set_meta("fallback", True)
                result.set_meta("fallback_reason", str(e))
        except Exception as e2:
            logger.error("Fallback extraction also failed: %s", e2)
            result = None

    elapsed = time.monotonic() - start_time
    logger.info("Total pipeline took %.1fs", elapsed)

    # 4. Guardar extracción (eliminando previa si existía por re-procesamiento)
    if result:
        if doc.extraction is not None:
            db.delete(doc.extraction)
            db.flush()

        extraction = Extraction(
            document_id=doc.id,
            doc_type=doc.doc_type.value,
            data=result.data,
            overall_confidence=compute_overall_confidence(result.data),
            llm_model=getattr(result, "llm_model", None),
            llm_primary=getattr(result, "llm_primary", False),
        )
        db.add(extraction)
        doc.status = DocStatus.EXTRACTED

        # Guardar regla aprendida automáticamente para este CUIT de emisor
        try:
            fields = result.data.get("fields", {})
            cuit_val = fields.get("emitter_cuit", {}).get("value") or fields.get("cuit", {}).get("value")
            emitter_name_val = fields.get("emitter_name", {}).get("value")
            if cuit_val:
                from app.services.rules_learning import save_learned_rule
                save_learned_rule(db, str(cuit_val), str(emitter_name_val or ""), result.data, user_id=doc.user_id)
        except Exception as e:
            logger.warning("No se pudo guardar la regla aprendida: %s", e)
    else:
        doc.status = DocStatus.FAILED
        doc.error_message = "No se pudo extraer contenido del PDF."

    doc.processed_at = doc.updated_at
    db.commit()
