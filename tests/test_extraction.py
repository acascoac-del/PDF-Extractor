"""Tests de integración: pipeline de extracción de factura completo."""
from __future__ import annotations

from pathlib import Path

from app.services.pdf_text import extract_text
from app.services.extraction.invoice import extract_invoice
from app.services.confidence import compute_overall_confidence


SAMPLE_PDF = Path(__file__).parent.parent / "storage" / "uploads" / "sample_invoice.pdf"


class TestInvoiceExtraction:
    """Test end-to-end de extracción de factura AFIP con PDF real."""

    def test_extract_text(self):
        if not SAMPLE_PDF.exists():
            return  # skip si no hay PDF de muestra
        content = extract_text(SAMPLE_PDF)
        assert content.page_count == 1
        assert content.char_count > 0
        assert not content.is_scanned

    def test_extract_invoice_fields(self):
        if not SAMPLE_PDF.exists():
            return
        content = extract_text(SAMPLE_PDF)
        result = extract_invoice(content)
        fields = result.data.get("fields", {})

        # CUIT
        assert fields["cuit"]["value"] == "30-71234567-9"
        assert fields["cuit"]["confidence"] >= 0.9

        # CAE
        assert fields["cae"]["value"] == "76123456789012"
        assert fields["cae"]["confidence"] >= 0.9

        # Invoice number
        assert fields["invoice_number"]["value"] == "0003-00000156"

        # Invoice type
        assert fields["invoice_type"]["value"] == "B"

        # Montos
        assert fields["net"]["value"] == 277500.0
        assert fields["iva_amount"]["value"] == 58275.0
        assert fields["total"]["value"] == 335775.0

        # Business name
        assert fields["business_name"]["value"] == "Distribuidora Sur SRL"

        # IVA condition
        assert fields["iva_condition"]["value"] == "Responsable Inscripto"

        # Dates
        assert fields["emission_date"]["value"] == "19/07/2026"
        assert fields["cae_expiry"]["value"] == "29/07/2026"

    def test_overall_confidence(self):
        if not SAMPLE_PDF.exists():
            return
        content = extract_text(SAMPLE_PDF)
        result = extract_invoice(content)
        conf = compute_overall_confidence(result.data)
        assert conf >= 0.7
        assert conf <= 1.0

    def test_all_fields_have_source(self):
        if not SAMPLE_PDF.exists():
            return
        content = extract_text(SAMPLE_PDF)
        result = extract_invoice(content)
        for key, field in result.data.get("fields", {}).items():
            assert "source" in field, f"Field {key} missing source"
            assert "confidence" in field, f"Field {key} missing confidence"
            assert "value" in field, f"Field {key} missing value"


class TestItemValidationAndAIFallback:
    """Pruebas de filtrado de ítems y fallback a IA cuando faltan ítems."""

    def test_is_valid_item(self):
        from app.services.extraction.invoice import _is_valid_item

        # Ítems válidos
        assert _is_valid_item({"description": "Nafta Super XXI", "quantity": 10, "unit_price": 1000, "subtotal": 10000})
        assert _is_valid_item({"description": "Aceite Sintetico 1L", "subtotal": 5500.5})

        # No ítems (encabezados, resumen impositivo, CUIT)
        assert not _is_valid_item({"description": "Subtotal", "subtotal": 10000})
        assert not _is_valid_item({"description": "IVA 21%", "quantity": 21, "subtotal": 2100})
        assert not _is_valid_item({"description": "Descripción", "quantity": 0})
        assert not _is_valid_item({"description": "CUIT: 30-12345678-9"})
        assert not _is_valid_item({"description": "Total", "import": 12100})

    def test_unknown_invoice_no_items_triggers_ai(self):
        """Factura desconocida (Axion) con CUIT/CAE/Fecha por reglas pero sin ítems -> IA completa."""
        from unittest.mock import MagicMock
        import json
        from app.services.pdf_text import PdfContent

        text = """
        AXION ENERGY ARGENTINA S.A.
        FACTURA 0005-00012345
        A ORIGINAL
        CUIT: 30-67890123-4
        Fecha: 20/07/2026
        Condición ante IVA: Responsable Inscripto
        SRES. Cliente Ejemplo SRL
        CUIT: 30-71234567-9
        CAE: 76123456789012
        Vencimiento CAE: 30/07/2026
        TOTAL: 50000.00
        """
        content = PdfContent(full_text=text, page_count=1, is_scanned=False, tables=[])

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content=json.dumps({
                        "emitter_name": "AXION ENERGY ARGENTINA S.A.",
                        "emitter_cuit": "30-67890123-4",
                        "receptor_cuit": "30-71234567-9",
                        "invoice_number": "0005-00012345",
                        "cae": "76123456789012",
                        "total": 50000.0,
                        "items": [
                            {
                                "code": "AX-01",
                                "description": "Combustible Axion Super",
                                "quantity": 40.0,
                                "unit": "L",
                                "unit_price": 1250.0,
                                "import": 50000.0,
                            }
                        ]
                    })
                )
            )
        ]
        mock_llm.chat.completions.create.return_value = mock_response
        mock_llm.model = "gpt-4o-mini"

        result = extract_invoice(content, llm_client=mock_llm)

        # Debe marcarse como extracción completa por IA
        assert result.llm_primary is True
        assert result.llm_model == "gpt-4o-mini"

        # Debe conservar encabezados de reglas de alta confianza
        fields = result.data.get("fields", {})
        assert fields["cuit"]["value"] == "30-67890123-4"
        assert fields["cae"]["value"] == "76123456789012"

        # Debe incluir los ítems extraídos por el LLM
        items = result.data.get("items", [])
        assert len(items) == 1
        assert items[0]["description"] == "Combustible Axion Super"
        assert items[0]["import"] == 50000.0
        assert items[0]["source"] == "llm"

