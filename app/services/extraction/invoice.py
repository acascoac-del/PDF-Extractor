"""Extractor de factura AFIP (tipo A/B/C).

Motor híbrido: regex para campos fijos (CUIT, CAE, fechas, montos) + LLM para
campos variables (descripción de ítems, forma de pago, etc.).
"""
from __future__ import annotations

import re
from typing import Any

from app.services.extraction.base import ExtractionResult
from app.services.pdf_text import PdfContent


def extract_invoice(content: PdfContent, llm_client=None, user=None) -> ExtractionResult:
    """Extrae campos de una factura argentina.

    Args:
        content: Texto y metadatos del PDF.
        llm_client: Cliente OpenAI ya creado (opcional).
        user: Usuario para crear cliente LLM desde sus settings (opcional).
    """
    result = ExtractionResult()
    full_text = content.full_text

    # Si nos pasan user pero no llm_client, crear uno desde los settings del usuario
    if llm_client is None and user is not None:
        from app.services.llm import get_client
        llm_client = get_client(user)

    # --- Número de factura ---
    result.set_field(
        "invoice_number",
        _extract_invoice_number(full_text),
        source="rules",
        confidence=0.85 if _extract_invoice_number(full_text) else 0.0,
    )

    # --- Letra de factura (A/B/C) ---
    result.set_field(
        "invoice_letter",
        _extract_invoice_letter(full_text),
        source="rules",
        confidence=0.80 if _extract_invoice_letter(full_text) else 0.0,
    )

    # --- Punto de venta ---
    result.set_field(
        "point_of_sale",
        _extract_point_of_sale(full_text),
        source="rules",
        confidence=0.80 if _extract_point_of_sale(full_text) else 0.0,
    )

    # --- CUIT del emisor (primer CUIT que aparece) ---
    result.set_field(
        "emitter_cuit",
        _extract_emitter_cuit(full_text),
        source="rules",
        confidence=0.90 if _extract_emitter_cuit(full_text) else 0.0,
    )

    # --- CUIT del receptor (segundo CUIT o el de "SRES.") ---
    result.set_field(
        "receptor_cuit",
        _extract_receptor_cuit(full_text),
        source="rules",
        confidence=0.90 if _extract_receptor_cuit(full_text) else 0.0,
    )

    # --- CUIT genérico (compatibilidad) ---
    result.set_field(
        "cuit",
        _extract_emitter_cuit(full_text),
        source="rules",
        confidence=0.95 if _extract_emitter_cuit(full_text) else 0.0,
    )

    # --- Razón social del emisor ---
    result.set_field(
        "emitter_name",
        _extract_emitter_name(full_text),
        source="rules",
        confidence=0.85 if _extract_emitter_name(full_text) else 0.0,
    )

    # --- Razón social del receptor ---
    result.set_field(
        "receptor_name",
        _extract_receptor_name(full_text),
        source="rules",
        confidence=0.85 if _extract_receptor_name(full_text) else 0.0,
    )

    # --- Razón social (genérico, compatibilidad) ---
    result.set_field(
        "business_name",
        _extract_emitter_name(full_text),
        source="rules",
        confidence=0.70 if _extract_emitter_name(full_text) else 0.0,
    )

    # --- Dirección del emisor ---
    result.set_field(
        "emitter_address",
        _extract_emitter_address(full_text),
        source="rules",
        confidence=0.80 if _extract_emitter_address(full_text) else 0.0,
    )

    # --- Dirección del receptor ---
    result.set_field(
        "receptor_address",
        _extract_receptor_address(full_text),
        source="rules",
        confidence=0.80 if _extract_receptor_address(full_text) else 0.0,
    )

    # --- IIBB del emisor ---
    result.set_field(
        "emitter_iibb",
        _extract_emitter_iibb(full_text),
        source="rules",
        confidence=0.85 if _extract_emitter_iibb(full_text) else 0.0,
    )

    # --- IIBB del receptor ---
    result.set_field(
        "receptor_iibb",
        _extract_receptor_iibb(full_text),
        source="rules",
        confidence=0.85 if _extract_receptor_iibb(full_text) else 0.0,
    )

    # --- Condición de IVA del emisor ---
    result.set_field(
        "emitter_iva_condition",
        _extract_emitter_iva_condition(full_text),
        source="rules",
        confidence=0.85 if _extract_emitter_iva_condition(full_text) else 0.0,
    )

    # --- Condición de IVA (genérico) ---
    result.set_field(
        "iva_condition",
        _extract_emitter_iva_condition(full_text),
        source="rules",
        confidence=0.90 if _extract_emitter_iva_condition(full_text) else 0.0,
    )

    # --- Fecha inicio actividades ---
    result.set_field(
        "emitter_start_date",
        _extract_emitter_start_date(full_text),
        source="rules",
        confidence=0.80 if _extract_emitter_start_date(full_text) else 0.0,
    )

    # --- Cuenta del receptor ---
    result.set_field(
        "receptor_account",
        _extract_receptor_account(full_text),
        source="rules",
        confidence=0.85 if _extract_receptor_account(full_text) else 0.0,
    )

    # --- Cuenta deudora del receptor ---
    result.set_field(
        "receptor_deudor_account",
        _extract_receptor_deudor_account(full_text),
        source="rules",
        confidence=0.85 if _extract_receptor_deudor_account(full_text) else 0.0,
    )

    # --- Incoterms ---
    result.set_field(
        "incoterms",
        _extract_incoterms(full_text),
        source="rules",
        confidence=0.85 if _extract_incoterms(full_text) else 0.0,
    )

    # --- Número SAP ---
    result.set_field(
        "sap_number",
        _extract_sap_number(full_text),
        source="rules",
        confidence=0.85 if _extract_sap_number(full_text) else 0.0,
    )

    # --- Número OC ---
    result.set_field(
        "oc_number",
        _extract_oc_number(full_text),
        source="rules",
        confidence=0.85 if _extract_oc_number(full_text) else 0.0,
    )

    # --- Condiciones de pago ---
    result.set_field(
        "payment_terms",
        _extract_payment_terms(full_text),
        source="rules",
        confidence=0.80 if _extract_payment_terms(full_text) else 0.0,
    )

    # --- Forma de envío ---
    result.set_field(
        "shipping_method",
        _extract_shipping_method(full_text),
        source="rules",
        confidence=0.80 if _extract_shipping_method(full_text) else 0.0,
    )

    # --- Condición de IVA ---
    result.set_field(
        "iva_condition",
        _extract_iva_condition(full_text),
        source="rules",
        confidence=0.90 if _extract_iva_condition(full_text) else 0.0,
    )

    # --- Fecha de emisión ---
    result.set_field(
        "emission_date",
        _extract_date(full_text),
        source="rules",
        confidence=0.85 if _extract_date(full_text) else 0.0,
    )

    # --- CAE (header) ---
    result.set_field(
        "cae",
        _extract_cae(full_text),
        source="rules",
        confidence=0.95 if _extract_cae(full_text) else 0.0,
    )

    # --- CAE de impresión (page 3 "CAE Nº") ---
    result.set_field(
        "invoice_cae",
        _extract_invoice_cae(full_text),
        source="rules",
        confidence=0.95 if _extract_invoice_cae(full_text) else 0.0,
    )

    # --- Vencimiento CAE ---
    result.set_field(
        "cae_expiry",
        _extract_cae_expiry(full_text),
        source="rules",
        confidence=0.80 if _extract_cae_expiry(full_text) else 0.0,
    )

    # --- Tipo de factura (A/B/C) ---
    result.set_field(
        "invoice_type",
        _detect_invoice_type(full_text),
        source="rules",
        confidence=0.75 if _detect_invoice_type(full_text) else 0.0,
    )

    # --- Totales ---
    # "neto gravado" / "neto" con word boundary
    result.set_field("net", _extract_amount_pattern(full_text, r"\bneto\b"), source="rules", confidence=0.70)
    # "IVA 21%: 58275" o "IVA: 58275" — NO matchear "condicion ante iva"
    iva_val = _extract_amount_pattern(full_text, r"\biva\s+\d+(?:\.\d+)?%\s*:")
    result.set_field("iva_amount", iva_val, source="rules", confidence=0.70)
    # "total" con word boundary para NO matchear "subtotal" ni "total tasa vial"
    result.set_field(
        "total", _extract_amount_pattern(full_text, r"\btotal\b(?!.*tasa\s+vial)"),
        source="rules", confidence=0.90,
    )

    # --- YPF-style totals ---
    # IMPORTE NETO
    result.set_field(
        "importe_neto",
        _extract_amount_pattern(full_text, r"importe\s+neto"),
        source="rules",
        confidence=0.80,
    )
    # FINANCIACION
    result.set_field(
        "financiacion",
        _extract_amount_pattern(full_text, r"financiaci[oó]n"),
        source="rules",
        confidence=0.80,
    )
    # ICL amount
    result.set_field(
        "icl_amount",
        _extract_amount_pattern(full_text, r"\bicl\b(?!\s+por)"),
        source="rules",
        confidence=0.80,
    )
    # IDC amount
    result.set_field(
        "idc_amount",
        _extract_amount_pattern(full_text, r"\bidc\b"),
        source="rules",
        confidence=0.80,
    )
    # IVA INSCRIPTO: "IVA INSCRIPTO: 21.00% 8.371.369,42" — skip past %
    iva_insc = _extract_amount_pattern(full_text, r"iva\s+inscripto(?:[^%]*%)?")
    result.set_field("iva_inscripto", iva_insc, source="rules", confidence=0.80)
    # IVA NO INSCRIPTO
    iva_no_insc = _extract_amount_pattern(full_text, r"iva\s+no\s+inscripto")
    result.set_field("iva_no_inscripto", iva_no_insc, source="rules", confidence=0.80)
    # IVA PERCEPCION: "IVA PERCEPCION: 3.00% 1.195.909,95" — skip past %
    iva_perc = _extract_amount_pattern(full_text, r"iva\s+percepci[oó]n(?:[^%]*%)?")
    result.set_field("iva_percepcion", iva_perc, source="rules", confidence=0.80)
    # IMPORTE ING. BRUTOS
    result.set_field(
        "ingresos_brutos",
        _extract_amount_pattern(full_text, r"ing(?:resos)?\.?\s*brutos|importe\s+ing\.?\s*brutos"),
        source="rules",
        confidence=0.80,
    )
    # TOTAL TASA VIAL — matchear "total tasa vial" NO "tasa vial ALDO BONZI"
    result.set_field(
        "tasa_vial",
        _extract_amount_pattern(full_text, r"total\s+tasa\s+vial"),
        source="rules",
        confidence=0.80,
    )
    # IVA percentage detection
    result.set_field(
        "iva_percentage",
        _extract_iva_percentage(full_text),
        source="rules",
        confidence=0.85,
    )

    # --- Ítems (desde tablas o líneas) ---
    items = _extract_items(content)
    result.add_items(items)

    # --- IBP entries (page 2) ---
    ibp_entries = _extract_ibp_entries(full_text)
    result.data["ibp_entries"] = ibp_entries

    # --- Tasa Vial entries (page 2) ---
    tasa_vial_entries = _extract_tasa_vial_entries(full_text)
    result.data["tasa_vial_entries"] = tasa_vial_entries

    # --- Risk/ONU descriptions ---
    risk_descriptions = _extract_risk_descriptions(full_text)
    result.data["risk_descriptions"] = risk_descriptions

    # --- Meta ---
    result.set_meta("page_count", content.page_count)
    result.set_meta("is_scanned", content.is_scanned)

    # --- LLM enrichment si hay cliente configurado ---
    if llm_client is not None:
        try:
            _enrich_with_llm(result, full_text, llm_client)
        except Exception:
            pass  # El LLM es opcional; si falla, nos quedamos con las reglas.

    return result


# ============ Funciones de regex ============

_CUIT_RE = re.compile(
    r"(?:CUIT|Cuit|cuit)[:\s]*(\d{2}[\-\./]?\d{8}[\-\./]?\d{1})"
)
# Match "FACTURA 1420-00197834" format (point of sale + invoice number)
_INVOICE_NUM_RE = re.compile(
    r"(?:FACTURA|Factura|N[roº°\.]?\s*(?:de\s+)?Factura|Comprobante)[\s:]*(\d{4}[\-\s]\d{8})"
)
_PV_RE = re.compile(r"(?:Punto\s*(?:de\s*)?Venta|PV)[\s:]*0*(\d{1,5})")
_DATE_RE = re.compile(
    r"(\d{1,2}[\s/\-\.]\d{1,2}[\s/\-\.]\d{2,4})"
)
_CAE_RE = re.compile(
    r"(?:CAE|C[Aa]e|Código\s*(?:de\s*)?Autorización)[\s:]*0*(\d{14})"
)
# CAE on page 3: "CAE Nº 86227967536513"
_INVOICE_CAE_RE = re.compile(
    r"CAE\s+N[ºo°]?\s*(\d{14})"
)
_CAE_EXP_RE = re.compile(
    r"(?:Vencimiento|Vto\.?|Venc\.?)(?:\s+(?:CAE|C[Aa]e))?[.:;\s]*(\d{1,2}[\s/\-\.]\d{1,2}[\s/\-\.]\d{2,4})"
)
_BIZ_NAME_RE = re.compile(
    r"(?:Raz[oó]n\s+Social|Denominaci[oó]n|Nombre)[\s:]+(.{2,80}?)(?:\n|$)"
)
_IVA_COND_RE = re.compile(
    r"(?:Condici[oó]n(?:\s+(?:ante\s+)?IVA)?|IVA)[\s:]*(Responsable\s+Inscripto|Monotributo|Exento|No\s+Inscripto|Consumidor\s+Final)",
    re.IGNORECASE,
)
_AMOUNT_RE = re.compile(
    r"(?:Neto\s+Gravado|Neto|IVA\s+21%?|Total|Importe\s+Total|TOTAL)\s*[:\$]?\s*[\$]?([\d.,]+)",
    re.IGNORECASE,
)

# Invoice letter: "A ORIGINAL" or "FACTURA A"
_INVOICE_LETTER_RE = re.compile(
    r"\b([ABC])\s+ORIGINAL\b", re.IGNORECASE
)

# Emitter CUIT: first CUIT in the document (appears with the emitter block)
_EMITTER_CUIT_RE = re.compile(
    r"CUIT[:\s]*(\d{2}[\-\./]?\d{8}[\-\./]?\d{1})"
)

# Receptor block: starts with "SRES." and contains CUIT
_RECEPTOR_NAME_RE = re.compile(
    r"SRES\.\s+(.+?)(?:\s+IVA\s|\s+CUIT)", re.IGNORECASE
)

# Receptor CUIT: the CUIT in the receptor block (after "SRES.")
_RECEPTOR_CUIT_RE = re.compile(
    r"SRES\..{5,200}?CUIT[:\s]*(\d{2}[\-\./]?\d{8}[\-\./]?\d{1})", re.IGNORECASE | re.DOTALL
)

# Emitter name: line after "FACTURA ..." that looks like a company name
_EMITTER_NAME_RE = re.compile(
    r"(?:FACTURA\s+\d{4}[\-\s]\d{8}\s*\n\s*[A-Z]\s+ORIGINAL\s*\n.*?\n)?"
    r"[A-Z][A-Z\s\.]+(?:S\.A\.|SA|SRL|S\.R\.L\.)",
    re.IGNORECASE
)

# Emitter address: line with street name + number, before CABA/Argentina
_EMITTER_ADDRESS_RE = re.compile(
    r"(BV\.?\s+MACACHA\s+GUEMES\s+\d+|AV\.?\s+[\w\s]+\d+|CALLE\s+[\w\s]+\d+)",
    re.IGNORECASE
)

# Receptor address: after "DOMICILIO:"
_RECEPTOR_ADDRESS_RE = re.compile(
    r"DOMICILIO[:\s]+(.+?)(?:\s+IIBB|\s+CAPITAL|\n)",
    re.IGNORECASE
)

# IIBB patterns
_EMITTER_IIBB_RE = re.compile(
    r"IIBB\s+CM[:\s]*(\d{2}[\-\./]?\d{7}[\-\./]?\d{1})"
)
_RECEPTOR_IIBB_RE = re.compile(
    r"IIBB\s+N[°oº]?[:\s]*(\d{10,11})"
)

# IVA condition for emitter (appears on its own line after address)
_EMITTER_IVA_COND_RE = re.compile(
    r"(IVA\s+RESPONSABLE\s+INSCRIPTO|IVA\s+MONOTRIBUTO|IVA\s+EXENTO|IVA\s+NO\s+INSCRIPTO|RESPONSABLE\s+INSCRIPTO)",
    re.IGNORECASE
)

# Start date: "FECHA INICIO ACTIVIDADES: 02/10/2023"
_START_DATE_RE = re.compile(
    r"FECHA\s+INICIO\s+ACTIVIDADES[:\s]+(\d{1,2}[\s/\-\.]\d{1,2}[\s/\-\.]\d{2,4})"
)

# Receptor account: "N° CUENTA: 2000170831"
_ACCOUNT_RE = re.compile(
    r"N[°oº]\s*CUENTA[:\s]+(\d+)"
)

# Receptor deudor account: "CUENTA DEUDORA: 122760407"
_DEUDOR_ACCOUNT_RE = re.compile(
    r"CUENTA\s+DEUDORA[:\s]+(\d+)"
)

# Incoterms: "INCOTERMS: CIF CIF Costes..."
_INCOTERMS_RE = re.compile(
    r"INCOTERMS[:\s]+(\w{2,5})\b", re.IGNORECASE
)

# SAP number: "N° SAP: 98452208"
_SAP_RE = re.compile(
    r"N[°oº]\s*SAP[:\s]+(\d+)"
)

# OC number: "OC: 0000105478CQ"
_OC_RE = re.compile(
    r"\bOC[:\s]+([\w]+)"
)

# Payment terms: "P. PAGO: dentro de los 20 días sin DPP"
_PAYMENT_TERMS_RE = re.compile(
    r"P\.?\s*PAGO[:\s]+(.+?)(?:\s+FORMA\s+DE\s+ENV[ÍI]O|\n)",
    re.IGNORECASE
)

# Shipping method: "FORMA DE ENVÍO: Mail"
_SHIPPING_METHOD_RE = re.compile(
    r"FORMA\s+DE\s+ENV[ÍI]O[:\s]+(.+?)(?:\n|$)",
    re.IGNORECASE
)

# IBP entries: "IBP Bs AS 1.50% 396.479,00"
_IBP_ENTRY_RE = re.compile(
    r"IBP\s+(.+?)\s+([\d.,]+)%\s+([\d.,]+)"
)

# Tasa Vial entries: "Tasa Vial ALDO BONZI: 4.401,87$"
_TASA_VIAL_ENTRY_RE = re.compile(
    r"Tasa\s+Vial\s+(.+?):\s*([\d.,]+)\s*\$"
)

# Risk/ONU descriptions: "NRO.RIESGO/ONU: 301202 GAS OIL O COMB. P/MOT DIESEL"
_RISK_DESC_RE = re.compile(
    r"NRO\.?RIESGO/?ONU[:\s]+(\d+)\s+(.+?)(?:\n|$)",
    re.IGNORECASE
)


def _clean_cuit(match: str) -> str:
    """Normaliza CUIT a formato XX-XXXXXXXX-X."""
    d = re.sub(r"[^\d]", "", match)
    if len(d) == 11:
        return f"{d[:2]}-{d[2:10]}-{d[10]}"
    return match


def _extract_cuit(text: str) -> str | None:
    m = _CUIT_RE.search(text)
    if m:
        return _clean_cuit(m.group(1))
    # Fallback: buscar formato CUIT suelto
    m2 = re.search(r"\b(\d{2}[\-\./]?\d{8}[\-\./]?\d{1})\b", text)
    if m2:
        return _clean_cuit(m2.group(1))
    return None


def _extract_emitter_cuit(text: str) -> str | None:
    """Extrae el CUIT del emisor (primer CUIT en el documento)."""
    m = _EMITTER_CUIT_RE.search(text)
    if m:
        return _clean_cuit(m.group(1))
    return None


def _extract_receptor_cuit(text: str) -> str | None:
    """Extrae el CUIT del receptor (en el bloque después de SRES.)."""
    m = _RECEPTOR_CUIT_RE.search(text)
    if m:
        return _clean_cuit(m.group(1))
    return None


def _extract_invoice_number(text: str) -> str | None:
    m = _INVOICE_NUM_RE.search(text)
    return m.group(1).strip() if m else None


def _extract_invoice_letter(text: str) -> str | None:
    """Extrae la letra de la factura (A/B/C) de 'A ORIGINAL'."""
    m = _INVOICE_LETTER_RE.search(text)
    if m:
        return m.group(1).upper()
    return None


def _extract_emitter_name(text: str) -> str | None:
    """Extrae la razón social del emisor (ej: 'YPF S.A.')."""
    # Buscar línea que contiene nombre de empresa + S.A./SRL/etc.
    m = _EMITTER_NAME_RE.search(text)
    if m:
        return m.group(0).strip()
    return None


def _extract_receptor_name(text: str) -> str | None:
    """Extrae la razón social del receptor (después de 'SRES.')."""
    m = _RECEPTOR_NAME_RE.search(text)
    if m:
        return m.group(1).strip()
    return None


def _extract_emitter_address(text: str) -> str | None:
    """Extrae la dirección del emisor."""
    m = _EMITTER_ADDRESS_RE.search(text)
    if m:
        return m.group(1).strip()
    return None


def _extract_receptor_address(text: str) -> str | None:
    """Extrae la dirección del receptor."""
    m = _RECEPTOR_ADDRESS_RE.search(text)
    if m:
        return m.group(1).strip()
    return None


def _extract_emitter_iibb(text: str) -> str | None:
    """Extrae el IIBB del emisor."""
    m = _EMITTER_IIBB_RE.search(text)
    if m:
        return m.group(1).strip()
    return None


def _extract_receptor_iibb(text: str) -> str | None:
    """Extrae el IIBB del receptor."""
    m = _RECEPTOR_IIBB_RE.search(text)
    if m:
        return m.group(1).strip()
    return None


def _extract_emitter_iva_condition(text: str) -> str | None:
    """Extrae la condición de IVA del emisor."""
    m = _EMITTER_IVA_COND_RE.search(text)
    if m:
        return m.group(1).strip().title()
    return None


def _extract_emitter_start_date(text: str) -> str | None:
    """Extrae la fecha de inicio de actividades."""
    m = _START_DATE_RE.search(text)
    if m:
        return m.group(1).strip()
    return None


def _extract_receptor_account(text: str) -> str | None:
    """Extrae el número de cuenta del receptor."""
    m = _ACCOUNT_RE.search(text)
    if m:
        return m.group(1).strip()
    return None


def _extract_receptor_deudor_account(text: str) -> str | None:
    """Extrae la cuenta deudora del receptor."""
    m = _DEUDOR_ACCOUNT_RE.search(text)
    if m:
        return m.group(1).strip()
    return None


def _extract_incoterms(text: str) -> str | None:
    """Extrae los incoterms."""
    m = _INCOTERMS_RE.search(text)
    if m:
        return m.group(1).strip().upper()
    return None


def _extract_sap_number(text: str) -> str | None:
    """Extrae el número SAP."""
    m = _SAP_RE.search(text)
    if m:
        return m.group(1).strip()
    return None


def _extract_oc_number(text: str) -> str | None:
    """Extrae el número de orden de compra."""
    m = _OC_RE.search(text)
    if m:
        return m.group(1).strip()
    return None


def _extract_payment_terms(text: str) -> str | None:
    """Extrae las condiciones de pago."""
    m = _PAYMENT_TERMS_RE.search(text)
    if m:
        return m.group(1).strip()
    return None


def _extract_shipping_method(text: str) -> str | None:
    """Extrae la forma de envío."""
    m = _SHIPPING_METHOD_RE.search(text)
    if m:
        return m.group(1).strip()
    return None


def _extract_invoice_cae(text: str) -> str | None:
    """Extrae el CAE de impresión de la página 3 ('CAE Nº ...')."""
    m = _INVOICE_CAE_RE.search(text)
    if m:
        return m.group(1).strip()
    return None


def _extract_point_of_sale(text: str) -> str | None:
    m = _PV_RE.search(text)
    return m.group(1) if m else None


def _extract_date(text: str) -> str | None:
    m = _DATE_RE.search(text)
    return m.group(1) if m else None


def _extract_cae(text: str) -> str | None:
    m = _CAE_RE.search(text)
    return m.group(1) if m else None


def _extract_cae_expiry(text: str) -> str | None:
    m = _CAE_EXP_RE.search(text)
    return m.group(1) if m else None


def _extract_business_name(text: str) -> str | None:
    m = _BIZ_NAME_RE.search(text)
    return m.group(1).strip() if m else None


def _extract_iva_condition(text: str) -> str | None:
    m = _IVA_COND_RE.search(text)
    return m.group(1).title() if m else None


def _extract_iva_percentage(text: str) -> float | None:
    """Detecta el porcentaje de IVA (21%, 10.5%, 27%, etc.)."""
    m = re.search(r"\biva\b[^0-9]*(\d+(?:[.,]\d+)?)\s*%", text, re.IGNORECASE)
    if m:
        return _parse_amount(m.group(1))
    return None


def _detect_invoice_type(text: str) -> str | None:
    text_l = text.lower()
    if "factura" not in text_l:
        return None
    if "factura electrónica" in text_l or "factura electronica" in text_l:
        if "credito" in text_l:
            return "B"
        if any(x in text_l for x in ["debito", "débito"]):
            return "A"
    for tipo in ["a", "b", "c"]:
        if f"factura {tipo}" in text_l:
            return tipo.upper()
    # Inferir por IVA: si menciona "gravado" o discriminación de IVA → A
    if any(x in text_l for x in ["gravado", "21%", "105%"]):
        return "A"
    if "consumidor final" in text_l:
        return "B"
    return None


def _parse_amount(raw: str) -> float | None:
    """Parsea un monto: detecta formato 1.234.567,89 (europeo) vs 1234567.89 (US)."""
    raw = raw.strip()
    if not raw:
        return None
    # Formato europeo: 1.234.567,89 → quitar puntos, cambiar coma por punto
    if "," in raw and "." in raw:
        return float(raw.replace(".", "").replace(",", "."))
    # Solo comas: 1234567,89 → cambiar coma por punto
    if "," in raw:
        return float(raw.replace(",", "."))
    # Solo puntos: puede ser 1.234.567 (miles) o 1234567.89 (decimal)
    if "." in raw:
        parts = raw.split(".")
        if len(parts[-1]) == 3 and len(parts) > 1:
            # Formato de miles: 1.234.567 → quitar puntos
            return float(raw.replace(".", ""))
        # Decimal: 1234567.89 → directo
    return float(raw)


def _extract_amount(text: str, label: str) -> float | None:
    """Busca monto asociado a un label (keyword)."""
    text_l = text.lower()
    label_l = label.lower()
    pattern = re.compile(
        rf"(?:{re.escape(label_l)})[^$\d]*[\$]?\s*([\d.,]+)",
        re.IGNORECASE,
    )
    m = pattern.search(text_l)
    if m:
        return _parse_amount(m.group(1))
    return None


def _extract_amount_pattern(text: str, label_pattern: str) -> float | None:
    """Busca monto con un regex de label complejo (para IVA con %, etc.)."""
    text_l = text.lower()
    pattern = re.compile(
        rf"(?:{label_pattern})[^$\d]*[\$]?\s*([\d.,]+)",
        re.IGNORECASE,
    )
    m = pattern.search(text_l)
    if m:
        return _parse_amount(m.group(1))
    return None


def _extract_ibp_entries(text: str) -> list[dict[str, Any]]:
    """Extrae las entradas IBP (Ingresos Brutos Provincial).

    Returns:
        Lista de dicts con keys: jurisdiction, percentage, amount.
    """
    entries: list[dict[str, Any]] = []
    for m in _IBP_ENTRY_RE.finditer(text):
        jurisdiction = m.group(1).strip()
        try:
            percentage = _parse_amount(m.group(2))
        except (ValueError, TypeError):
            percentage = None
        try:
            amount = _parse_amount(m.group(3))
        except (ValueError, TypeError):
            amount = None
        entries.append({
            "jurisdiction": jurisdiction,
            "percentage": percentage,
            "amount": amount,
        })
    return entries


def _extract_tasa_vial_entries(text: str) -> list[dict[str, Any]]:
    """Extrae las entradas de Tasa Vial por localidad.

    Returns:
        Lista de dicts con keys: locality, amount.
    """
    entries: list[dict[str, Any]] = []
    for m in _TASA_VIAL_ENTRY_RE.finditer(text):
        locality = m.group(1).strip()
        try:
            amount = _parse_amount(m.group(2))
        except (ValueError, TypeError):
            amount = None
        entries.append({
            "locality": locality,
            "amount": amount,
        })
    return entries


def _extract_risk_descriptions(text: str) -> list[dict[str, str]]:
    """Extrae las descripciones de riesgo/ONU.

    Returns:
        Lista de dicts con keys: number, description.
    """
    entries: list[dict[str, str]] = []
    for m in _RISK_DESC_RE.finditer(text):
        entries.append({
            "number": m.group(1).strip(),
            "description": m.group(2).strip(),
        })
    return entries


def _extract_items(content: PdfContent) -> list[dict[str, Any]]:
    """Extrae items: primero intenta tablas, luego texto libre como fallback."""
    # 1) Intentar extracción desde tablas (pdfplumber)
    items = _extract_items_from_tables(content)

    # 2) Si no se encontraron items, intentar extracción desde texto
    if not items:
        items = _extract_items_from_text(content)

    return items


def _extract_items_from_tables(content: PdfContent) -> list[dict[str, Any]]:
    """Intenta extraer ítems de las tablas detectadas por pdfplumber."""
    items: list[dict] = []
    # Recorrer tablas de todas las páginas
    all_tables: list = []
    for page_tables in content.tables:
        for tbl in page_tables:
            all_tables.append(tbl)

    for tbl in all_tables:
        if len(tbl) < 2:
            continue
        # Ignorar filas de encabezado (primeras)
        for row in tbl[1:]:
            item: dict[str, Any] = {}
            # Intentar mapear columnas
            if len(row) >= 4:
                # Patrón: descripción, cantidad, PU, subtotal
                item["description"] = row[0] if row[0] else ""
                try:
                    item["quantity"] = float(
                        str(row[-3] or "0").replace(".", "").replace(",", ".")
                    )
                except ValueError:
                    item["quantity"] = None
                try:
                    item["unit_price"] = float(
                        str(row[-2] or "0").replace(".", "").replace(",", ".")
                    )
                except ValueError:
                    item["unit_price"] = None
                try:
                    item["subtotal"] = float(
                        str(row[-1] or "0").replace(".", "").replace(",", ".")
                    )
                except ValueError:
                    item["subtotal"] = None
            else:
                item["description"] = " ".join(str(c) for c in row if c)

            if any(v for k, v in item.items() if k != "description" and v is not None):
                item["source"] = "table"
                item["confidence"] = 0.60
                items.append(item)

    return items


# Regex para línea principal de item (YPF-style):
#   CODIGO  DESCRIPCION  CANTIDAD  UM  RIESGO  VALOR_UNITARIO  IMPORTE
# Ejemplo: 401200 DIESEL 500 3.783,300 L 301202 1.501,749 5.681.568,52
_ITEM_LINE_RE = re.compile(
    r"^(\d{6})\s+"           # CODIGO (6 dígitos)
    r"(.+?)\s+"              # DESCRIPCION (variable, non-greedy)
    r"([\d.,]+)\s+"          # CANTIDAD
    r"(L|EN|KG|UN)\s+"       # UM
    r"(\d+)\s+"              # RIESGO/ONU
    r"([\d.,]+)\s+"          # VALOR UNITARIO
    r"([\d.,]+)$",           # IMPORTE
    re.MULTILINE,
)

# Regex alternativo más flexible (sin RIESGO o con formato distinto)
_ITEM_LINE_FLEX_RE = re.compile(
    r"^(\d{6})\s+"           # CODIGO
    r"(.+?)\s+"              # DESCRIPCION
    r"([\d.,]+)\s+"          # CANTIDAD
    r"(L|EN|KG|UN)\s+"       # UM
    r"(\d+)\s+"              # RIESGO/ONU (puede ser 1 o más dígitos)
    r"([\d.,]+)\s+"          # VALOR UNITARIO
    r"([\d.,]+)$",           # IMPORTE
    re.MULTILINE,
)

# Líneas modificadoras que pertenecen al item anterior
_MODIFIER_RE = re.compile(
    r"^(ICL\s+por\s+litro\s+[\d.,]+\s+[\$]/L\s+[\d.,]+\s+L)"  # ICL por litro
    r"|^(B%:\s*[\d.,]+\s+[\d.,]+\s+L)"                         # B% bonificación
    r"|^(E%:\s*[\d.,]+\s+[\d.,]+\s+L)",                        # E% extra
    re.MULTILINE,
)


def _extract_items_from_text(content: PdfContent) -> list[dict[str, Any]]:
    """Extrae items parseando líneas de texto (para PDFs sin tablas, ej. YPF)."""
    items: list[dict[str, Any]] = []

    full_text = content.full_text
    if not full_text:
        return items

    # Encontrar todas las líneas principales de items
    main_matches = list(_ITEM_LINE_RE.finditer(full_text))
    if not main_matches:
        # Intentar regex flexible como fallback
        main_matches = list(_ITEM_LINE_FLEX_RE.finditer(full_text))

    if not main_matches:
        return items

    # Construir lista de (start, end, match) para items principales
    item_spans = [(m.start(), m.end(), m) for m in main_matches]

    # Encontrar todas las líneas modificadoras
    modifier_matches = list(_MODIFIER_RE.finditer(full_text))

    for idx, (start, end, m) in enumerate(item_spans):
        item: dict[str, Any] = {
            "code": m.group(1),
            "description": m.group(2).strip(),
            "quantity": _parse_amount(m.group(3)),
            "unit": m.group(4),
            "risk_un": m.group(5),
            "unit_price": _parse_amount(m.group(6)),
            "import": _parse_amount(m.group(7)),
            "modifiers": [],
            "source": "rules",
            "confidence": 0.50,
        }

        # Determinar el rango de texto entre este item y el siguiente
        next_start = item_spans[idx + 1][0] if idx + 1 < len(item_spans) else len(full_text)

        # Asignar líneas modificadoras que caen entre este item y el siguiente
        for mod_m in modifier_matches:
            mod_start = mod_m.start()
            if start < mod_start < next_start:
                # Capturar el texto completo de la línea modificadora
                modifier_text = mod_m.group(0).strip()
                if modifier_text:
                    item["modifiers"].append(modifier_text)

        items.append(item)

    return items


def _enrich_with_llm(result: ExtractionResult, text: str, llm_client) -> None:
    """Usa el LLM para enriquecer/corregir campos que las reglas no encontraron."""
    from app.services.llm import extract_invoice_with_llm

    llm_data = extract_invoice_with_llm(text, llm_client)
    if not llm_data:
        return

    fields = result.data.get("fields", {})
    for key, value in llm_data.items():
        if key in fields and fields[key]["value"] is None and value is not None:
            fields[key] = {
                "value": value,
                "source": "llm",
                "confidence": 0.75,
                "raw": value,
            }
    result.data["fields"] = fields
    result.llm_model = getattr(llm_client, "model", None)
