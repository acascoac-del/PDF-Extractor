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
