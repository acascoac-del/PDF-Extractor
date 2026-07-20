"""Tests de reglas de extracción (regex) para facturas AFIP."""
from __future__ import annotations

from app.services.extraction.invoice import (
    _extract_cuit,
    _extract_cae,
    _extract_date,
    _extract_business_name,
    _extract_iva_condition,
    _detect_invoice_type,
    _parse_amount,
    _extract_invoice_number,
    _extract_point_of_sale,
)


class TestCUIT:
    def test_cuit_con_guiones(self):
        assert _extract_cuit("CUIT: 30-71234567-9") == "30-71234567-9"

    def test_cuit_sin_guiones(self):
        assert _extract_cuit("CUIT: 30712345679") == "30-71234567-9"

    def test_cuit_con_otros_separadores(self):
        assert _extract_cuit("CUIT: 30.71234567.9") == "30-71234567-9"

    def test_cuit_no_encontrado(self):
        assert _extract_cuit("no hay cuit aqui") is None


class TestCAE:
    def test_cae_normal(self):
        assert _extract_cae("CAE: 76123456789012") == "76123456789012"

    def test_cae_con_prefijo(self):
        assert _extract_cae("Código Autorización: 76123456789012") == "76123456789012"

    def test_cae_no_encontrado(self):
        assert _extract_cae("no hay cae") is None


class TestDates:
    def test_fecha_slash(self):
        assert _extract_date("Fecha: 19/07/2026") == "19/07/2026"

    def test_fecha_guion(self):
        assert _extract_date("Fecha: 19-07-2026") == "19-07-2026"

    def test_fecha_corta(self):
        assert _extract_date("Fecha: 19/07/26") == "19/07/26"


class TestBusinessName:
    def test_razon_social(self):
        assert _extract_business_name("Razón Social: Distribuidora Sur SRL") == "Distribuidora Sur SRL"

    def test_denominacion(self):
        assert _extract_business_name("Denominación: Mi Empresa SA") == "Mi Empresa SA"

    def test_no_encontrado(self):
        assert _extract_business_name("texto random") is None


class TestIVACondition:
    def test_responsable_inscripto(self):
        assert _extract_iva_condition("Condición ante IVA: Responsable Inscripto") == "Responsable Inscripto"

    def test_monotributo(self):
        assert _extract_iva_condition("IVA: Monotributo") == "Monotributo"

    def test_consumidor_final(self):
        assert _extract_iva_condition("IVA: Consumidor Final") == "Consumidor Final"


class TestInvoiceType:
    def test_factura_b(self):
        assert _detect_invoice_type("FACTURA B\nPunto de Venta: 0003") == "B"

    def test_factura_a(self):
        assert _detect_invoice_type("FACTURA A\nIVA 21%") == "A"

    def test_no_factura(self):
        assert _detect_invoice_type("Este documento no es una factura") is None


class TestInvoiceNumber:
    def test_numero_factura(self):
        assert _extract_invoice_number("Nro. Factura: 0003-00000156") == "0003-00000156"

    def test_comprobante(self):
        assert _extract_invoice_number("Comprobante: 0005-00000012") == "0005-00000012"


class TestPointOfSale:
    def test_pv(self):
        assert _extract_point_of_sale("Punto de Venta: 0003") == "3"

    def test_pv_miles(self):
        assert _extract_point_of_sale("PV: 0042") == "42"


class TestParseAmount:
    def test_formato_decimal(self):
        assert _parse_amount("277500.00") == 277500.0

    def test_formato_entero(self):
        assert _parse_amount("1000") == 1000.0

    def test_formato_europeo(self):
        assert _parse_amount("1.234.567,89") == 1234567.89

    def test_formato_miles_sin_decimal(self):
        assert _parse_amount("1.234.567") == 1234567.0

    def test_formato_coma_decimal(self):
        assert _parse_amount("277500,50") == 277500.5

    def test_formato_mixto(self):
        assert _parse_amount("1.234.567,00") == 1234567.0
