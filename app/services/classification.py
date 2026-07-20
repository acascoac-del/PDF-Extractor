"""Clasificación y pipeline de extracción.

Fase 5 lo completa con reglas + LLM.
Por ahora: clasificación básica por keywords y pipeline que marca estado.
"""
from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.document import DocStatus, DocType, Document
from app.models.extraction import Extraction
from app.services.pdf_text import extract_text


# Keywords para clasificación rápida (reglas)
_KEYWORDS: dict[DocType, list[str]] = {
    DocType.INVOICE: [
        "factura", "comprobante fiscal", "cae", "cuit", "razón social",
        "condición de iva", "punto de venta", "nro. factura", "n° de factura",
        "codigo autorizacion", "fecha de emision", "subtotal", "total",
        "importe", "gravado", "no gravado", "exento", "neto",
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


def run_pipeline_sync(doc: Document, pdf_path: Path, db: Session, user=None) -> None:
    """Pipeline síncrono completo: texto → clasificación → extracción.

    En Fase 11 esto se migra a Celery como tarea asíncrona.
    """
    doc.status = DocStatus.PROCESSING
    db.commit()

    # 1. Extraer texto
    content = extract_text(pdf_path)
    doc.page_count = content.page_count
    doc.is_scanned = content.is_scanned
    doc.needs_ocr = content.is_scanned

    # 2. Clasificar (si no tiene tipo seteado por el usuario)
    if doc.doc_type is None or doc.doc_type_source != "user":
        classify_document(doc, content.full_text)
    db.commit()

    # 3. Extraer datos según tipo
    from app.services.extraction.invoice import extract_invoice
    from app.services.extraction.base import ExtractionResult
    from app.services.confidence import compute_overall_confidence

    result: ExtractionResult | None = None

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

        result = extract_generic(content)

    # 4. Guardar extracción
    if result:
        extraction = Extraction(
            document_id=doc.id,
            doc_type=doc.doc_type.value,
            data=result.data,
            overall_confidence=compute_overall_confidence(result.data),
            llm_model=getattr(result, "llm_model", None),
        )
        db.add(extraction)
        doc.status = DocStatus.EXTRACTED
    else:
        doc.status = DocStatus.FAILED
        doc.error_message = "No se pudo extraer contenido."

    doc.processed_at = doc.updated_at
    db.commit()
