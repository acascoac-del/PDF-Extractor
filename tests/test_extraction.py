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

    def test_clean_json_response(self):
        from app.services.llm import clean_json_response

        # JSON directo
        assert clean_json_response('{"foo": "bar"}') == {"foo": "bar"}

        # Markdown fenced
        assert clean_json_response('```json\n{"foo": "bar"}\n```') == {"foo": "bar"}

        # Con etiquetas <think> cerradas (DeepSeek R1 en Groq)
        think_resp = """<think>
        Analyzing invoice text...
        Found fields...
        </think>
        ```json
        {"invoice_number": "0001-00001234", "total": 1500.0}
        ```"""
        assert clean_json_response(think_resp) == {"invoice_number": "0001-00001234", "total": 1500.0}

        # Con etiquetas <think> sin cerrar por truncamiento
        unclosed_think_resp = """<think>
        Here's a thinking process:
        1. Analyze user input: extract fields from invoice
        {"invoice_number": "0001-00005555", "total": 2500.0}"""
        assert clean_json_response(unclosed_think_resp) == {"invoice_number": "0001-00005555", "total": 2500.0}

        # Texto explicativo alrededor del JSON
        text_around = "Here is the JSON response:\n{\"items\": [{\"description\": \"Item 1\"}]}\nHope it helps!"
        assert clean_json_response(text_around) == {"items": [{"description": "Item 1"}]}

    def test_get_client_user_settings(self, monkeypatch):
        import app.services.llm as llm_module
        from unittest.mock import MagicMock

        mock_openai_cls = MagicMock()
        monkeypatch.setattr(llm_module, "OpenAI", mock_openai_cls)

        user = MagicMock()
        user.settings = {
            "llm": {
                "provider": "openrouter",
                "api_key": "sk-or-v1-test",
                "base_url": "https://openrouter.ai/api/v1",
                "model": "deepseek/deepseek-r1",
                "temperature": 0.2,
            }
        }

        client = llm_module.get_client(user)
        assert client is not None
        from app.config import settings
        mock_openai_cls.assert_called_once_with(
            base_url="https://openrouter.ai/api/v1",
            api_key="sk-or-v1-test",
            timeout=float(settings.llm_timeout),
            default_headers={
                "HTTP-Referer": "https://pdf-extractor.app",
                "X-Title": "PDF Extractor",
            },
        )
        model, temp = llm_module._get_model_and_temperature(user, client)
        assert model == "deepseek/deepseek-r1"
        assert temp == 0.2

    def test_summary_breakdown_axion_style(self):
        from app.services.extraction.invoice import _build_summary_breakdown

        fields = {
            "subtotal": {"value": 329028.11},
            "iva_amount": {"value": 69095.90},
            "iibb": {"value": 5950.53},
            "tasas_municipales": {"value": 0.0},
            "sellos": {"value": 0.0},
            "percepcion_iva": {"value": 0.0},
            "itc": {"value": 60749.94},
            "co2": {"value": 6924.00},
            "total": {"value": 471748.48},
        }

        breakdown = _build_summary_breakdown(fields)
        labels = [item["label"] for item in breakdown]
        assert "Subtotal" in labels
        assert "IVA" in labels
        assert "IIBB" in labels
        assert "ITC" in labels
        assert "CO2" in labels
        assert "Total en Pesos" in labels

    def test_pae_6_column_table_and_text_extraction(self):
        from app.services.pdf_text import PdfContent
        from app.services.extraction.invoice import _extract_items

        # Simular tabla de 6 columnas de factura Pan American Energy / Expreso Malargüe
        tbl_header = ["Cod. Prod.", "Descripción", "Cantidad", "Unidad", "BASE FOCO", "Importe"]
        tbl_row1 = ["000000011435", "BS QUANTUM DIESEL X10 - 0983", "498,00", "L", "1.922,35", "957.332,15"]
        tbl_row2 = ["0000000200728", "B 5000 QUANTUM DIESEL ZONA FRIA 0894", "53,71", "L", "1.798,81", "111.600,14"]

        content = PdfContent(
            full_text="Factura PAE\n000000011435 BS QUANTUM DIESEL X10 - 0983 498,00 L 1.922,35 957.332,15",
            page_count=1,
            is_scanned=False,
            tables=[[[tbl_header, tbl_row1, tbl_row2]]],
        )

        items = _extract_items(content)
        assert len(items) == 2
        assert items[0]["description"] == "BS QUANTUM DIESEL X10 - 0983"
        assert items[0]["code"] == "000000011435"
        assert items[0]["quantity"] == 498.0
        assert items[0]["unit"] == "L"
        assert items[0]["unit_price"] == 1922.35
        assert items[0]["subtotal"] == 957332.15

        assert items[1]["description"] == "B 5000 QUANTUM DIESEL ZONA FRIA 0894"
        assert items[1]["quantity"] == 53.71

    def test_groq_provider_defaults(self, monkeypatch):
        import app.services.llm as llm_module
        from unittest.mock import MagicMock

        mock_openai_cls = MagicMock()
        monkeypatch.setattr(llm_module, "OpenAI", mock_openai_cls)

        user = MagicMock()
        user.settings = {
            "llm": {
                "provider": "groq",
                "api_key": "gsk_test_key",
                "base_url": "",
                "model": "gpt-4o-mini",  # invalido para groq
                "temperature": 0.0,
            }
        }

        client = llm_module.get_client(user)
        assert client is not None
        mock_openai_cls.assert_called_once_with(
            base_url="https://api.groq.com/openai/v1",
            api_key="gsk_test_key",
            timeout=float(llm_module.settings.llm_timeout),
        )
        model, temp = llm_module._get_model_and_temperature(user, client)
        assert model == "llama-3.3-70b-versatile"
        assert temp == 0.0

    def test_openrouter_provider_defaults(self, monkeypatch):
        import app.services.llm as llm_module
        from unittest.mock import MagicMock

        mock_openai_cls = MagicMock()
        monkeypatch.setattr(llm_module, "OpenAI", mock_openai_cls)

        user = MagicMock()
        user.settings = {
            "llm": {
                "provider": "openrouter",
                "api_key": "sk-or-test",
                "base_url": "",
                "model": "gpt-4o-mini",  # invalido sin prefijo para openrouter
                "temperature": 0.1,
            }
        }

        client = llm_module.get_client(user)
        assert client is not None
        mock_openai_cls.assert_called_once_with(
            base_url="https://openrouter.ai/api/v1",
            api_key="sk-or-test",
            timeout=float(llm_module.settings.llm_timeout),
            default_headers={
                "HTTP-Referer": "https://pdf-extractor.app",
                "X-Title": "PDF Extractor",
            },
        )
        model, temp = llm_module._get_model_and_temperature(user, client)
        assert model == "qwen/qwen-2.5-72b-instruct"
        assert temp == 0.1

    def test_multipage_continuation_and_copy_filtering(self):
        from app.services.pdf_text import PdfContent
        from app.services.extraction.invoice import _extract_items

        # Caso 1: Multipágina con continuación (Hoja 1 de 2, Hoja 2 de 2)
        tbl1_h = ["Cód.", "Descripción", "Cant.", "U.M", "P. Unit", "Importe"]
        tbl1_r = ["1001", "PRODUCTO HOJA 1", "10", "UN", "100,00", "1.000,00"]

        tbl2_h = ["Cód.", "Descripción", "Cant.", "U.M", "P. Unit", "Importe"]
        tbl2_r = ["1002", "PRODUCTO HOJA 2", "5", "UN", "200,00", "1.000,00"]

        content_continuation = PdfContent(
            page_count=2,
            pages_text=[
                "FACTURA A N° 0001-00001234 ORIGINAL Hoja 1 de 2",
                "FACTURA A N° 0001-00001234 ORIGINAL Hoja 2 de 2",
            ],
            tables=[
                [[tbl1_h, tbl1_r]],
                [[tbl2_h, tbl2_r]],
            ],
        )

        unique_pages = content_continuation.get_unique_pages()
        assert len(unique_pages) == 2

        items = _extract_items(content_continuation)
        assert len(items) == 2
        assert items[0]["description"] == "PRODUCTO HOJA 1"
        assert items[1]["description"] == "PRODUCTO HOJA 2"

        # Caso 2: Multipágina con copias (Page 1 ORIGINAL, Page 2 DUPLICADO de la misma página)
        content_copy = PdfContent(
            page_count=2,
            pages_text=[
                "FACTURA A N° 0001-00001234 ORIGINAL Hoja 1 de 1\n1001 PRODUCTO A 10 UN 100 1000",
                "FACTURA A N° 0001-00001234 DUPLICADO Hoja 1 de 1\n1001 PRODUCTO A 10 UN 100 1000",
            ],
            tables=[
                [[tbl1_h, tbl1_r]],
                [[tbl1_h, tbl1_r]],  # Duplicado exacto
            ],
        )

        unique_copy_pages = content_copy.get_unique_pages()
        assert len(unique_copy_pages) == 1
        assert unique_copy_pages[0][0] == 0

        copy_items = _extract_items(content_copy)
        assert len(copy_items) == 1
        assert copy_items[0]["description"] == "PRODUCTO HOJA 1"

    def test_strix_8_page_anexo_extraction(self):
        from app.services.pdf_text import PdfContent
        from app.services.extraction.invoice import _extract_items

        # Simular 8 páginas de Anexo Strix (como en la imagen del usuario)
        tbl_header = ["Cantidad", "Descripción", "Período", "Precio Total"]
        
        pages_text = []
        tables = []
        for page_num in range(1, 9):
            p_text = f"strix ANEXO DE FACTURA A N° 0012-01611655\nCliente 1205667 CUIT: 30-70808111-2 Página {page_num}"
            p_rows = [tbl_header]
            for r in range(1, 11):
                patente_num = f"PAT{page_num:02d}{r:02d}"
                p_rows.append([
                    "6,00",
                    f"620900 - Servicios de informática - Abono Strix Flotas Logistica (ACC000{page_num}{r}) - Patente {patente_num}",
                    "01/07/2026 AL 31/07/2026",
                    "26317.62"
                ])
            pages_text.append(p_text)
            tables.append([p_rows])

        strix_content = PdfContent(
            page_count=8,
            pages_text=pages_text,
            tables=tables,
        )

        unique_pages = strix_content.get_unique_pages()
        assert len(unique_pages) == 8

        items = _extract_items(strix_content)
        # Deben extraerse las 80 líneas (10 por cada una de las 8 páginas)
        assert len(items) == 80
        assert items[0]["code"] == "620900"
        assert "Patente PAT0101" in items[0]["description"]
        assert items[0]["quantity"] == 6.0
        assert items[0]["subtotal"] == 26317.62
        assert items[0]["unit_price"] == 4386.27
        assert items[-1]["description"].endswith("PAT0810")

    def test_strix_text_anexo_keeps_each_vehicle_item(self):
        from app.services.pdf_text import PdfContent
        from app.services.extraction.invoice import _extract_items

        text = (
            "ANEXO DE FACTURA A Nº 0012-01611655\n"
            "Cantidad Descripción Período Precio Total\n"
            "6.00 620900 - Servicios de informática - Abono Strix Flotas Logistica "
            "01/07/2026 AL 31/07/2026 26317.62\n"
            "(ACC000008415500) - Patente OAF640\n"
            "1.00 620900 - Servicios de informática - Abono Strix Flotas Logistica "
            "01/07/2026 AL 31/07/2026 14917.38\n"
            "(ACC100297700283) - Patente AF118QB"
        )
        content = PdfContent(page_count=1, pages_text=[text], full_text=text)

        items = _extract_items(content)

        assert len(items) == 2
        assert "Patente OAF640" in items[0]["description"]
        assert items[0]["import"] == 26317.62
        assert items[0]["unit_price"] == 4386.27
        assert "Patente AF118QB" in items[1]["description"]

    def test_auto_learning_emitter_rules(self, monkeypatch):
        from unittest.mock import MagicMock
        import app.services.rules_learning as rl_module

        monkeypatch.setattr(rl_module, "select", MagicMock())
        monkeypatch.setattr(rl_module, "EmitterRule", MagicMock())

        db = MagicMock()
        mock_rule = MagicMock()
        mock_rule.use_count = 1
        mock_rule.emitter_cuit = "30-70808111-2"
        db.execute.return_value.scalars.return_value.first.return_value = mock_rule

        rule = rl_module.get_learned_rule(db, "30-70808111-2")
        assert rule is not None
        assert rule.emitter_cuit == "30-70808111-2"

        result_data = {
            "fields": {
                "emitter_cuit": {"value": "30-70808111-2", "source": "llm"},
                "total": {"value": 2169810.66, "source": "llm"},
            },
            "items": [{"description": "Servicios Strix"}],
        }

        updated = rl_module.save_learned_rule(db, "30-70808111-2", "Strix", result_data)
        assert updated is not None
        assert updated.use_count == 2







