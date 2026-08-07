"""Extractor genérico (fallback)."""
from __future__ import annotations

from app.services.extraction.base import ExtractionResult
from app.services.pdf_text import PdfContent


def extract_generic(content: PdfContent, user=None) -> ExtractionResult:
    result = ExtractionResult()
    result.set_field("page_count", content.page_count, source="rules", confidence=1.0)
    result.set_field("char_count", content.char_count, source="rules", confidence=1.0)
    result.set_meta("full_text", content.full_text)
    result.set_meta("is_scanned", content.is_scanned)

    # Si hay un proveedor de IA configurado por el usuario, realizar extracción por IA
    try:
        from app.services.llm import get_client, extract_invoice_with_llm, _get_model_and_temperature
        llm_client = get_client(user)
        if llm_client is not None:
            model_name, _ = _get_model_and_temperature(user=user, client=llm_client)
            llm_data = extract_invoice_with_llm(content.full_text, client=llm_client, user=user)
            if llm_data:
                result.llm_model = model_name
                fields = result.data.get("fields", {})
                for k, v in llm_data.items():
                    if k in ("items", "summary_breakdown") or v is None or v == "":
                        continue
                    fields[k] = {"value": v, "source": "llm", "confidence": 0.85, "raw": v}
                result.data["fields"] = fields
                if llm_data.get("items"):
                    result.data["items"] = llm_data["items"]
                if llm_data.get("summary_breakdown"):
                    result.data["summary_breakdown"] = llm_data["summary_breakdown"]
    except Exception:
        pass

    return result
