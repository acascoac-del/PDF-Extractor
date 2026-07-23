"""Extractor de facturas de peaje / autopista (TelePase).

Maneja los distintos formatos de las concesionarias viales argentinas:
AUBASA, AUSA, Autopistas del Sol, CEAMSE, Autovia del Mercosur,
Grupo Concesionario del Oeste, Corredores Viales.
"""
from __future__ import annotations

import re
from typing import Any

from app.services.extraction.base import ExtractionResult
from app.services.pdf_text import PdfContent


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

_PEAJE_KEYWORDS = [
    "telepase", "pasadas", "transacciones telepase",
    "peaje", "cat.", "cat 1", "cat 2", "cat 3", "cat 4",
    "cat 5", "cat 6", "cat 7", "cat 8",
    "autopista", "aubasa", "ceamse",
    "grupo concesionario del oeste", "autovia del mercosur",
    "corredores viales", "autopistas del sol", "autopistas urbanas",
    "bonificacion gs. administr",
    "gastos administrativos",
]


def is_peaje_invoice(text: str) -> bool:
    """Return True if the text looks like a toll-road / peaje invoice."""
    text_l = text.lower()
    hits = sum(1 for kw in _PEAJE_KEYWORDS if kw in text_l)
    # Need at least 2 keyword hits to be confident, OR one very specific one
    if hits >= 2:
        return True
    if "transacciones telepase" in text_l:
        return True
    # SI code pattern combined with CAT pattern is a strong signal
    if re.search(r"SI\d{10,}", text) and re.search(r"CAT\.?\s*\d", text_l):
        return True
    return False


# ---------------------------------------------------------------------------
# Main extractor
# ---------------------------------------------------------------------------

def extract_peaje(content: PdfContent, user=None) -> ExtractionResult:
    """Extract toll-road invoice data."""
    result = ExtractionResult()
    full_text = content.full_text

    # --- Standard invoice header fields ---
    _extract_header_fields(result, full_text)

    # --- Peaje-specific header fields ---
    _extract_peaje_header(result, full_text)

    # --- Items ---
    items = _extract_peaje_items(content)
    result.add_items(items)

    # --- Totals ---
    _extract_peaje_totals(result, full_text)

    # --- Meta ---
    result.set_meta("page_count", content.page_count)
    result.set_meta("is_scanned", content.is_scanned)
    result.set_meta("invoice_subtype", "peaje")

    return result


# ---------------------------------------------------------------------------
# Header extraction
# ---------------------------------------------------------------------------

def _extract_header_fields(result: ExtractionResult, text: str) -> None:
    """Extract standard invoice header fields shared with regular invoices."""
    # Invoice number
    # Formats: "FACTURA\n\n0758-00311497" or "FACTURA 5009-02027645" or standalone "00700-03257277"
    m = re.search(
        r"(?:FACTURA(?:\s+TELEPASE)?|N[roº°\.]?\s*(?:de\s+)?Factura|Comprobante)"
        r"[\s:\n]*(\d{4,5}[\-\s]\d{6,8})",
        text, re.IGNORECASE,
    )
    if not m:
        # Fallback: standalone NNNNN-NNNNNNNN on its own line
        m = re.search(r"\b(\d{4,5}-\d{6,8})\b", text)
    result.set_field(
        "invoice_number", m.group(1).strip() if m else None,
        source="rules", confidence=0.85 if m else 0.0,
    )

    # Invoice letter
    m = re.search(r"\b([ABC])\s+ORIGINAL\b", text, re.IGNORECASE)
    result.set_field(
        "invoice_letter", m.group(1).upper() if m else None,
        source="rules", confidence=0.80 if m else 0.0,
    )

    # Point of sale
    m = re.search(r"(?:Punto\s*(?:de\s*)?Venta|PV|Código\s*N[°º]?)[:\s]*0*(\d{1,5})", text, re.IGNORECASE)
    result.set_field(
        "point_of_sale", m.group(1) if m else None,
        source="rules", confidence=0.80 if m else 0.0,
    )

    # Emitter CUIT
    m = re.search(r"CUIT\s*N[°º.:]*\s*(\d{2}[\-\./]?\d{8}[\-\./]?\d{1})", text)
    result.set_field(
        "emitter_cuit", _clean_cuit(m.group(1)) if m else None,
        source="rules", confidence=0.90 if m else 0.0,
    )

    # Receptor CUIT (always 30-70781613-5 for Compania Distribuidora)
    m = re.search(r"CUIT\s*(\d{2}[\-\./]?\d{8}[\-\./]?\d{1})", text)
    # Find the CUIT that belongs to the receptor (after "Señores" or near "COMPANIA DISTRIBUIDORA")
    receptor_cuit = None
    receptor_block = re.search(
        r"(?:Se[ñn]or(?:es)?|COMPANIA\s+DISTRIBUIDORA).{0,500}?CUIT\s*[:\s]*(\d{2}[\-\./]?\d{8}[\-\./]?\d{1})",
        text, re.IGNORECASE | re.DOTALL,
    )
    if receptor_block:
        receptor_cuit = _clean_cuit(receptor_block.group(1))
    result.set_field(
        "receptor_cuit", receptor_cuit,
        source="rules", confidence=0.90 if receptor_cuit else 0.0,
    )

    # CUIT generic
    result.set_field(
        "cuit", _clean_cuit(m.group(1)) if m else None,
        source="rules", confidence=0.95 if m else 0.0,
    )

    # Emitter name
    emitter_name = _extract_emitter_name_peaje(text)
    result.set_field(
        "emitter_name", emitter_name,
        source="rules", confidence=0.85 if emitter_name else 0.0,
    )
    result.set_field(
        "business_name", emitter_name,
        source="rules", confidence=0.70 if emitter_name else 0.0,
    )

    # Receptor name
    result.set_field(
        "receptor_name", "COMPANIA DISTRIBUIDORA",
        source="rules", confidence=0.90,
    )

    # Emission date
    m = re.search(r"Fecha[:\s]+(\d{1,2}[\s/\-\.]\d{1,2}[\s/\-\.]\d{2,4})\b", text)
    result.set_field(
        "emission_date", m.group(1).strip() if m else None,
        source="rules", confidence=0.85 if m else 0.0,
    )

    # CAE
    m = re.search(r"CAE[:\s]*0*(\d{14})", text)
    result.set_field(
        "cae", m.group(1) if m else None,
        source="rules", confidence=0.95 if m else 0.0,
    )
    result.set_field(
        "invoice_cae", m.group(1) if m else None,
        source="rules", confidence=0.95 if m else 0.0,
    )

    # CAE expiry
    m = re.search(r"(?:VTO|Vencimiento|Vence)[:\.\s]+(\d{1,2}[\s/\-\.]\d{1,2}[\s/\-\.]\d{2,4})", text)
    result.set_field(
        "cae_expiry", m.group(1).strip() if m else None,
        source="rules", confidence=0.80 if m else 0.0,
    )

    # IVA condition
    m = re.search(
        r"(IVA\s+RESP(?:ONSABLE)?\s+INSCRIPTO|IVA\s+MONOTRIBUTO|IVA\s+EXENTO|RESPONSABLE\s+INSCRIPTO)",
        text, re.IGNORECASE,
    )
    result.set_field(
        "emitter_iva_condition", m.group(1).strip().title() if m else None,
        source="rules", confidence=0.85 if m else 0.0,
    )
    result.set_field(
        "iva_condition", m.group(1).strip().title() if m else None,
        source="rules", confidence=0.90 if m else 0.0,
    )

    # Invoice type
    result.set_field(
        "invoice_type", "A",
        source="rules", confidence=0.90,
    )


def _extract_emitter_name_peaje(text: str) -> str | None:
    """Extract the emitter company name from a peaje invoice."""
    # Try common peaje company names
    patterns = [
        r"(GRUPO\s+CONCESIONARIO\s+DEL\s+OESTE\s+S\.?A\.?)",
        r"(CORREDORES\s+VIALES\s+S\.?A\.?)",
        r"(AUTOVIA\s+DEL\s+MERCOSUR\s+S\.?\.?A\.?U\.?)",
        r"(AUTOPISTAS\s+DEL\s+SOL\s+S\.?A\.?)",
        r"(AUTOPISTAS\s+de\s+BUENOS\s+AIRES\s+S\.?A\.?)",
        r"(AUTOPISTAS\s+URBANAS\s+S\.?A\.?)",
        r"(C\.?E\.?A\.?M\.?S\.?E\.?)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()

    # Generic fallback: first line that looks like a company name
    m = re.search(r"([A-Z][A-Z\s\.]+(?:S\.A\.|SA|SRL|S\.R\.L\.|S\.A\.U\.))", text)
    return m.group(1).strip() if m else None


def _extract_peaje_header(result: ExtractionResult, text: str) -> None:
    """Extract peaje-specific header fields."""
    # Road company name
    road_company = _extract_emitter_name_peaje(text)
    result.data["road_company"] = road_company

    # Road company CUIT
    m = re.search(r"CUIT\s*N[°º.:]*\s*(\d{2}[\-\./]?\d{8}[\-\./]?\d{1})", text)
    road_cuit = _clean_cuit(m.group(1)) if m else None
    result.data["road_cuit"] = road_cuit

    # Period - supports "al" separator (01/07/26 al 15/07/26) and space (01/07/2026 07/07/2026)
    period_match = re.search(
        r"(?:Per[ií]odo(?:\s+Facturado)?[:\s]*)(\d{1,2}[\s/\-\.]\d{1,2}[\s/\-\.]\d{2,4})\s+(?:al|a)\s+(\d{1,2}[\s/\-\.]\d{1,2}[\s/\-\.]\d{2,4})",
        text, re.IGNORECASE,
    )
    if period_match:
        result.data["period_start"] = period_match.group(1).strip()
        result.data["period_end"] = period_match.group(2).strip()
    else:
        # Try space-separated dates (AUSA format)
        period_alt = re.search(
            r"(?:Per[ií]odo(?:\s+facturado)?[:\s]*)(\d{1,2}[\s/\-\.]\d{1,2}[\s/\-\.]\d{2,4})\s+(\d{1,2}[\s/\-\.]\d{1,2}[\s/\-\.]\d{2,4})",
            text, re.IGNORECASE,
        )
        if period_alt:
            result.data["period_start"] = period_alt.group(1).strip()
            result.data["period_end"] = period_alt.group(2).strip()
        else:
            # Try "DATE al DATE" without Período prefix (AUBASA format:
            # "CUIT 30-70781613-5 01/07/26 al 15/07/26")
            period_al = re.search(
                r"(\d{1,2}[\s/\-\.]\d{1,2}[\s/\-\.]\d{2,4})\s+(?:al|a)\s+(\d{1,2}[\s/\-\.]\d{1,2}[\s/\-\.]\d{2,4})",
                text, re.IGNORECASE,
            )
            if period_al:
                result.data["period_start"] = period_al.group(1).strip()
                result.data["period_end"] = period_al.group(2).strip()
            else:
                result.data["period_start"] = None
                result.data["period_end"] = None

    # First due date and amount
    # Formats: "Fecha 1º Vto 05/08/26 $ 20.347,71" or "1er. Vto.: 10/08/2026 $ 66.498,0"
    # or "Vencimiento: 22/07/2026" or "1er Vencimiento 22/07/2026 2.808.273,79"
    _DATE = r"\d{1,2}[\s/\-\.]\d{1,2}[\s/\-\.](?:\d{4}|\d{2})(?!\d)"
    vto1 = re.search(
        r"(?:Fecha\s+)?1[ºo°e]?r?\.?\s*(?:Vto\.?|Vencimiento)[:\s]*"
        rf"({_DATE})\s*\$?\s*([\d.,]+)",
        text, re.IGNORECASE,
    )
    if vto1:
        result.data["first_due_date"] = vto1.group(1).strip()
        result.data["first_due_amount"] = _parse_amount(vto1.group(2))
    else:
        # Try date only (CEAMSE: amount on separate line)
        vto1_date_only = re.search(
            r"(?:Fecha\s+)?1[ºo°e]?r?\.?\s*(?:Vto\.?|Vencimiento)[:\s]*"
            rf"({_DATE})",
            text, re.IGNORECASE,
        )
        if vto1_date_only:
            result.data["first_due_date"] = vto1_date_only.group(1).strip()
            # Look for amount on the same line or nearby
            line_start = text.rfind("\n", 0, vto1_date_only.start()) + 1
            line_end = text.find("\n", vto1_date_only.end())
            if line_end < 0:
                line_end = len(text)
            line_text = text[line_start:line_end]
            amt_m = re.search(r"\$\s*([\d.,]+)", line_text)
            result.data["first_due_amount"] = _parse_amount(amt_m.group(1)) if amt_m else None
        else:
            # AUSA format: "Vencimiento: 22/07/2026"
            vto_ausa = re.search(
                rf"Vencimiento[:\s]+({_DATE})",
                text, re.IGNORECASE,
            )
            result.data["first_due_date"] = vto_ausa.group(1).strip() if vto_ausa else None
            result.data["first_due_amount"] = None

    # Second due date and amount
    vto2 = re.search(
        r"2[ºo°]?\.?\s*(?:Vto\.?|Vencimiento)[:\s]*"
        rf"({_DATE})\s*\$?\s*([\d.,]+)",
        text, re.IGNORECASE,
    )
    if vto2:
        result.data["second_due_date"] = vto2.group(1).strip()
        result.data["second_due_amount"] = _parse_amount(vto2.group(2))
    else:
        # Try date only, then look for C/RECARGO or TOTAL CON RECARGO amount
        vto2_date_only = re.search(
            r"2[ºo°]?\.?\s*(?:Vto\.?|Vencimiento)[:\s]*"
            rf"({_DATE})",
            text, re.IGNORECASE,
        )
        if vto2_date_only:
            result.data["second_due_date"] = vto2_date_only.group(1).strip()
            # Look for C/RECARGO or TOTAL CON RECARGO amount nearby
            recargo = re.search(r"(?:C/RECARGO|TOTAL CON RECARGO)\s+([\d.,]+)", text, re.IGNORECASE)
            if recargo:
                result.data["second_due_amount"] = _parse_amount(recargo.group(1))
            else:
                result.data["second_due_amount"] = None
        else:
            result.data["second_due_date"] = None
            result.data["second_due_amount"] = None

    # Payment method
    m = re.search(
        r"(?:ser[aá]\s+debitada\s+de\s+la\s+tarjeta|tarjeta)\s+(AMERICAN\s+EXPRESS|AMEX|VISA|MASTERCARD)",
        text, re.IGNORECASE,
    )
    result.data["payment_method"] = m.group(1).upper() if m else None

    # Client code
    m = re.search(
        r"(?:Cliente|C[oó]digo(?:\s+de)?\s+Cliente)[:\s]*(\d{15}(?:/\d+)?)",
        text, re.IGNORECASE,
    )
    if m:
        result.data["client_code"] = m.group(1).strip()
    else:
        m2 = re.search(r"(908030707816135\d*)", text)
        result.data["client_code"] = m2.group(1) if m2 else None

    # Also store as standard fields
    result.set_field("road_company", road_company, source="rules", confidence=0.90 if road_company else 0.0)
    result.set_field("road_cuit", road_cuit, source="rules", confidence=0.90 if road_cuit else 0.0)
    result.set_field("period_start", result.data.get("period_start"), source="rules", confidence=0.85 if result.data.get("period_start") else 0.0)
    result.set_field("period_end", result.data.get("period_end"), source="rules", confidence=0.85 if result.data.get("period_end") else 0.0)
    result.set_field("first_due_date", result.data.get("first_due_date"), source="rules", confidence=0.80 if result.data.get("first_due_date") else 0.0)
    result.set_field("first_due_amount", result.data.get("first_due_amount"), source="rules", confidence=0.80 if result.data.get("first_due_amount") else 0.0)
    result.set_field("second_due_date", result.data.get("second_due_date"), source="rules", confidence=0.80 if result.data.get("second_due_date") else 0.0)
    result.set_field("second_due_amount", result.data.get("second_due_amount"), source="rules", confidence=0.80 if result.data.get("second_due_amount") else 0.0)
    result.set_field("payment_method", result.data.get("payment_method"), source="rules", confidence=0.85 if result.data.get("payment_method") else 0.0)
    result.set_field("client_code", result.data.get("client_code"), source="rules", confidence=0.85 if result.data.get("client_code") else 0.0)


# ---------------------------------------------------------------------------
# Item extraction
# ---------------------------------------------------------------------------

# Pattern for qty+CAT items: QTY DESCRIPTION CAT[. N] [SI...] AMOUNT
# Works with finditer on arbitrary text (not anchored to line start).
# Examples:
#   "4 PASADAS TELEPASE-CAT.5 SI9093436470 9859,32"
#   "1 RICCHERI-CAT 3 SI9094951040 2148.76"
#   "2 PEAJE DOCK SUD-CAT.3 SI9091950701 11129.38"
#   "1 ALBERTI-CAT.2 SI900061206238-HP 1.381,56"
#   "6 TRANSACCIONES TELEPASE - CAT 4 35702,46"
_PEAJE_QTY_ITEM_RE = re.compile(
    r"(?<![.,\d])(\d+)\s+"                       # quantity (not part of decimal)
    r"(.+?)"                                     # description (non-greedy)
    r"CAT\.?\s*(\d+)"                            # category
    r"(?:\s+SI(\d+)(?:-(HP|HN))?\s+"             # optional SI code + HP/HN
    r"|[\s:]+"                                   # OR just whitespace
    r")"
    r"([\d.,]+)"                                 # amount
    r"(?=\s|$|GASTOS|BONIFIC|SI\d|\d+\s)",       # lookahead: boundary
    re.IGNORECASE,
)

# Items without quantity (GASTOS ADMINISTRATIVOS, BONIFICACION)
# "GASTOS ADMINISTRATIVOS 12.40"
# "BONIFICACION GS. ADMINIST. -0.01"
_PEAJE_NO_QTY_RE = re.compile(
    r"(GASTOS\s+ADMINISTRATIVOS|BONIFICACI[OÓ]N\s+GS\.?\s*ADMINIST\.?)\s+"
    r"(-?[\d.,]+)",
    re.IGNORECASE,
)

# Standalone SI code: "SI9093436470 0,00" or just "SI9091950701"
_PEAJE_SI_RE = re.compile(
    r"(SI\d+(?:-HP|-HN)?)\s*(-?[\d.,]+)?",
)


def _extract_peaje_items(content: PdfContent) -> list[dict[str, Any]]:
    """Parse peaje items from all pages, handling all known formats."""
    items: list[dict[str, Any]] = []

    # Process each page separately to handle multi-page invoices
    for page_text in content.pages_text:
        if not page_text:
            continue
        page_items = _parse_peaje_items_from_text(page_text)
        items.extend(page_items)

    return items


def _parse_peaje_items_from_text(text: str) -> list[dict[str, Any]]:
    """Parse peaje items from a single page of text.

    Uses finditer to scan for all qty+CAT patterns and no-qty items.
    Handles two-column layouts by finding multiple matches per line.
    """
    items: list[dict[str, Any]] = []
    pending_si: str | None = None  # SI code carried from standalone line

    # Find the item section
    item_section = _find_item_section(text)
    if not item_section:
        item_section = text

    lines = item_section.split("\n")
    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue

        # Skip header-like lines
        if re.match(r"^(Cantidad|Cant)\s+Descripci", line_stripped, re.IGNORECASE):
            continue
        if line_stripped.startswith("Esta factura"):
            break
        if line_stripped.startswith("Usted dispone"):
            break

        # Check for standalone SI code line (CEAMSE / Autopistas del Sol format)
        si_m = _PEAJE_SI_RE.fullmatch(line_stripped)
        if si_m:
            pending_si = si_m.group(1)
            continue

        # Find all qty+CAT items on this line (handles two-column layouts)
        qty_matches = list(_PEAJE_QTY_ITEM_RE.finditer(line_stripped))
        if qty_matches:
            for m in qty_matches:
                si_code = (m.group(4) if m.group(4) else None) or pending_si
                hp_hn = m.group(5).upper() if m.group(5) else _extract_hp_hn(m.group(2))
                item = _make_item(
                    qty=m.group(1), desc=m.group(2), cat=m.group(3),
                    amount=m.group(6), si_code=si_code, hp_hn=hp_hn,
                )
                items.append(item)
            pending_si = None

        # Also check for no-qty items on this line (GASTOS ADMINISTRATIVOS, BONIFICACION)
        for nq_m in _PEAJE_NO_QTY_RE.finditer(line_stripped):
            desc = nq_m.group(1).strip()
            amount = _parse_amount(nq_m.group(2))
            unit = "BONIFICACION" if "bonific" in desc.lower() else "GASTO"
            items.append({
                "code": None,
                "description": desc,
                "quantity": 1,
                "unit": unit,
                "category": None,
                "unit_price": amount,
                "import": amount,
                "hp_hn": None,
                "source": "rules",
                "confidence": 0.70,
            })

    return items


def _find_item_section(text: str) -> str | None:
    """Find the section of text containing line items."""
    # Start after header indicators
    start = 0
    for marker in ["Cantidad Descripci", "Cant Descripci", "Cant\tDescripci"]:
        idx = text.find(marker)
        if idx != -1:
            start = idx + len(marker)
            break

    # End at footer indicators
    end = len(text)
    for marker in ["Esta factura ser", "Subtotal ", "SUBTOTAL ", "Usted dispone"]:
        idx = text.find(marker, start)
        if idx != -1:
            end = min(end, idx)

    if start >= end:
        return None
    return text[start:end]


def _make_item(
    qty: str, desc: str, cat: str | None, amount: str,
    si_code: str | None, hp_hn: str | None,
) -> dict[str, Any]:
    """Build a standardized item dict."""
    desc = desc.strip().rstrip("-").strip()
    quantity = _parse_amount(qty)
    import_amount = _parse_amount(amount)

    # Determine unit
    desc_l = desc.lower()
    if "transaccion" in desc_l:
        unit = "TRANSACCION"
    elif "pasada" in desc_l:
        unit = "PASADA"
    else:
        unit = "PASADA"  # default for peaje

    return {
        "code": si_code,
        "description": desc,
        "quantity": quantity,
        "unit": unit,
        "category": cat,
        "unit_price": round(import_amount / quantity, 2) if quantity and import_amount else None,
        "import": import_amount,
        "hp_hn": hp_hn,
        "source": "rules",
        "confidence": 0.75,
    }


def _extract_hp_hn(text: str) -> str | None:
    """Extract HP or HN indicator from text."""
    m = re.search(r"\b(HP|HN)\b", text, re.IGNORECASE)
    return m.group(1).upper() if m else None


def _extract_si_code(text: str) -> str | None:
    """Extract SI code from text."""
    m = re.search(r"(SI\d+(?:-HP|-HN)?)", text)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Totals extraction
# ---------------------------------------------------------------------------

def _extract_peaje_totals(result: ExtractionResult, text: str) -> None:
    """Extract totals from a peaje invoice.

    Handles multiple formats:
    Format A (standard):
        Subtotal IVA Resp.Inscripto IVA Resp.No Inscr. Percepción IIBB PCIA Percepción IB CABA TOTAL
        16.760,89 3.519,78 0,00 67,04 0,00 20.347,71

    Format B (Autopistas del Sol):
        67.536,48 6,75 67.543,23 14.182,66 0,00 0,00 270,15 2.026,10 84.022,14
        Subtotal Perc. IB CABA Res Subtotal IVA Inscripto IVA no Insc. RAE* Perc. IB BsAs Perc. IVA R.G.

    Format C (CEAMSE):
        SUBTOTAL IMPUESTOS SUBTOTAL IVA INSCRIPTO IVA NO INSC. PERCEPCION PERCEPCION TOTAL
        53.563,64 0,00 53.563,64 11.248,36 0,00 1.606,91 214,25 66.633,16

    Format D (AUSA):
        Gravado No Gravado IVA RG.212 RG 3337 IIBB CEF Total
        2.095.568,17 2,74 440.069,40 62.867,05 209,56 209.556,87
        Total
        2.808.273,79

    Format E (AUBASA):
        Subtotal IVA IVA Resp.No Inscr. IVA RG.3337 Percepción II.BB. TOTAL
        53.450,73 11.224,66 0,00 1.603,52 Bs.As. 213,80 66.498,06
    """
    text_l = text.lower()

    # --- Subtotal ---
    # Patterns match the label SEGMENT (keyword to next keyword boundary).
    subtotal = _find_total_value(text, [
        r"subtotal\s+perc",           # "Subtotal Perc. IB CABA Res"
        r"subtotal\s+impuestos",      # "SUBTOTAL IMPUESTOS"
        r"\bsubtotal\b",              # "Subtotal" (standalone)
        r"\bgravado\b",               # "Gravado" (AUSA)
    ])
    result.set_field("subtotal", subtotal, source="rules", confidence=0.80 if subtotal else 0.0)

    # --- IVA Inscripto ---
    iva_insc = _find_total_value(text, [
        r"iva\s+resp\.?\s*inscripto",  # "IVA Resp.Inscripto"
        r"iva\s+inscripto",            # "IVA INSCRIPTO" / "IVA Inscripto"
        r"iva\s+rg\.?\s*212",          # "IVA RG.212" (AUSA)
        r"(?<!\w)iva(?!\s*(?:resp|no\s|rg\b))",  # standalone "IVA" (AUBASA)
    ])
    result.set_field("iva_inscripto", iva_insc, source="rules", confidence=0.80 if iva_insc else 0.0)

    # --- IVA No Inscripto ---
    iva_no_insc = _find_total_value(text, [
        r"iva\s+resp\.?\s*no\s+insc",  # "IVA Resp.No Inscr."
        r"iva\s+no\s+insc",            # "IVA NO INSC."
    ])
    result.set_field("iva_no_inscripto", iva_no_insc, source="rules", confidence=0.80 if iva_no_insc else 0.0)

    # --- Percepcion IIBB (PCIA / Provincia) ---
    perc_iibb = _find_total_value(text, [
        r"percepci[oó]n\s+iibb\s+p",  # "Percepción IIBB PCIA"
        r"percepci[oó]n\s+iibb",      # "Percepción IIBB"
        r"percepci[oó]n\s+ii\.?bb",   # "Percepción II.BB."
        r"perc\.\s*ib\s+bs\.?\s*as",  # "Perc. IB BsAs"
    ])
    result.set_field("percepcion_iibb", perc_iibb, source="rules", confidence=0.70 if perc_iibb else 0.0)

    # --- Percepcion IB CABA ---
    perc_caba = _find_total_value(text, [
        r"percepci[oó]n\s+ib\s+caba",  # "Percepción IB CABA"
    ])
    result.set_field("percepcion_ib_caba", perc_caba, source="rules", confidence=0.70 if perc_caba else 0.0)

    # --- Total ---
    total = _extract_peaje_total(text)
    result.set_field("total", total, source="rules", confidence=0.90 if total else 0.0)
    result.data["total"] = total

    # --- IVA RG 3337 ---
    iva_rg = _find_total_value(text, [
        r"iva\s+rg\.?\s*3337",         # "IVA RG.3337"
        r"perc\.\s*iva\s+rg",          # "Perc. IVA R.G."
        r"perc\.\s*iva\s+r\.?g\.?",    # "Perc. IVA RG"
    ])
    result.set_field("iva_rg", iva_rg, source="rules", confidence=0.70 if iva_rg else 0.0)

    # --- Percepcion IB BsAs ---
    perc_bsas = _find_total_value(text, [
        r"percepci[oó]n\s+ib\s+bs\.?\s*as",  # "Percepción IB Bs.As."
        r"perc\.\s*ib\s+bs\.?\s*as",          # "Perc. IB BsAs"
        r"ii\.?bb\.\s*bs\.?\s*as",            # "II.BB. Bs.As."
    ])
    result.set_field("percepcion_ib_bsas", perc_bsas, source="rules", confidence=0.70 if perc_bsas else 0.0)


def _find_total_value(text: str, label_patterns: list[str]) -> float | None:
    """Find a numeric value associated with one of the label patterns.

    Strategy:
    1. Find the totals labels line (backward search, skip headers).
    2. Find the amounts line (near the labels line, with 3+ decimal amounts).
    3. Build a list of (label_text, amount_value) pairs by matching each
       amount to the label keyword region that precedes it.
    4. For each label pattern, find the pair whose label_text matches.
    """
    lines = text.split("\n")

    # 1. Find the labels line
    labels_line_idx = _find_labels_line(lines)
    if labels_line_idx < 0:
        return None

    labels_line = lines[labels_line_idx].strip()

    # 2. Find the amounts line
    _DECIMAL_RE = re.compile(r'(?<![.\d])(\d{1,3}(?:\.\d{3})+,\d+|\d+,\d{2,})(?!\s*%)')
    amounts_line_idx, amounts, amount_positions = _find_amounts_line(
        lines, labels_line_idx, _DECIMAL_RE
    )
    if amounts_line_idx < 0 or not amounts:
        return None

    amounts_line = lines[amounts_line_idx].strip()
    amounts_line_len = max(len(amounts_line), 1)
    labels_len = max(len(labels_line), 1)

    # 3. Find all known label keywords on the labels line, ordered by position.
    _LABEL_KW_RE = re.compile(
        r'subtotal\s+impuestos|subtotal(?!\s+impuestos)|'
        r'iva\s+resp\.?\s*inscripto|iva\s+inscripto|'
        r'iva\s+resp\.?\s*no\s+insc\.?|iva\s+no\s+insc\.?|'
        r'iva\s+rg\.?\s*\d+|iva\b|'
        r'percepci[oó]n|perc\.\s*iva|perc\.|'
        r'gravado|no\s+gravado|rae|rg\s+\d+|total',
        re.IGNORECASE,
    )
    kw_matches = list(_LABEL_KW_RE.finditer(labels_line))
    kw_entries = [(m.start(), m.end(), m.group()) for m in kw_matches]

    # 4. Map each amount to the closest keyword whose start column is
    #    closest to the amount's column position on the amounts line.
    #    Both lines are column-aligned, so character positions correspond
    #    directly (no proportional scaling needed).
    pairs: list[tuple[str, float]] = []
    used_kw: set[int] = set()
    for ai, apos in enumerate(amount_positions):
        # Find the closest unused keyword by column position
        best_ki = -1
        best_dist = float('inf')
        for ki, (kstart, kend, ktext) in enumerate(kw_entries):
            if ki in used_kw:
                continue
            dist = abs(kstart - apos)
            if dist < best_dist:
                best_dist = dist
                best_ki = ki
        if best_ki < 0:
            continue
        used_kw.add(best_ki)
        # Build label text from this keyword to the next
        kstart = kw_entries[best_ki][0]
        if best_ki + 1 < len(kw_entries):
            label_end = kw_entries[best_ki + 1][0]
        else:
            label_end = labels_len
        label_text = labels_line[kstart:label_end].strip()
        pairs.append((label_text, amounts[ai]))

    # 5. For each label pattern, find the first pair whose label matches.
    #    If no pair matches, fall back to matching against the full labels
    #    line and mapping by proportional position.
    for pat in label_patterns:
        for label_text, amount_val in pairs:
            if re.search(pat, label_text, re.IGNORECASE):
                return amount_val
        # Fallback: match against full labels line
        all_matches = list(re.finditer(pat, labels_line, re.IGNORECASE))
        if all_matches:
            m = all_matches[-1]
            mid_frac = (m.start() + m.end()) / 2 / labels_len
            mapped_pos = mid_frac * amounts_line_len
            best_ai = min(
                range(len(amount_positions)),
                key=lambda i: abs(amount_positions[i] - mapped_pos)
            )
            return amounts[best_ai]

    return None


def _find_labels_line(lines: list[str]) -> int:
    """Find the totals labels line by searching backward."""
    for i in range(len(lines) - 1, -1, -1):
        ll = lines[i].strip().lower()
        # Skip lines that are headers (contain CUIT:, "ing.brutos", "responsable")
        if any(skip in ll for skip in ["cuit:", "ing.brutos", "responsable", "ing. brutos"]):
            continue
        kw_count = sum(1 for kw in ["subtotal", "iva", "percepci", "total", "gravado"]
                       if kw in ll)
        if kw_count >= 2:
            return i
    return -1


def _find_amounts_line(
    lines: list[str], labels_idx: int, pattern: re.Pattern,
) -> tuple[int, list[float], list[int]]:
    """Find the amounts line and return (idx, amounts, char_positions)."""
    best_idx = -1
    best_amounts: list[float] = []
    best_positions: list[int] = []
    best_count = 0
    for offset in range(1, 6):
        for direction in [1, -1]:
            idx = labels_idx + direction * offset
            if idx < 0 or idx >= len(lines):
                continue
            line = lines[idx].strip()
            if not line or re.match(r'^[\d.,\s]+%[\d.,\s%]*$', line):
                continue
            amounts = []
            positions = []
            for m in pattern.finditer(line):
                val = _parse_amount(m.group(1))
                if val is not None:
                    amounts.append(val)
                    positions.append(m.start())
            if len(amounts) >= 3 and len(amounts) > best_count:
                best_count = len(amounts)
                best_amounts = amounts
                best_positions = positions
                best_idx = idx
    return best_idx, best_amounts, best_positions


def _extract_peaje_total(text: str) -> float | None:
    """Extract the grand total from a peaje invoice.

    Strategy: find "TOTAL" label and grab the number. For multi-line totals
    sections, take the last large number.
    """
    # Try "TOTAL A PAGAR" first (most reliable)
    m = re.search(r"TOTAL\s+A\s+PAGAR\s+([\d.,]+)", text, re.IGNORECASE)
    if m:
        return _parse_amount(m.group(1))

    # Try "TOTAL" followed by amount on same line
    # Be careful not to match "TOTAL TASA VIAL" or "TOTAL CON RECARGO"
    m = re.search(r"\bTOTAL\b(?:\s+CON\s+RECARGO)?[^\n]*?\$?\s*([\d.,]+)", text, re.IGNORECASE)
    if m:
        val = _parse_amount(m.group(1))
        # Sanity: total should be a reasonably large number
        if val and val > 100:
            return val

    # For Format B (Autopistas del Sol): amounts on one line, labels on next
    # Look for the pattern: "N1 N2 N3 ... TOTAL" where N values are in a line
    # and TOTAL is the last label
    totals_line = re.search(
        r"(\d[\d.,]+)\s+(\d[\d.,]+)\s+(\d[\d.,]+)\s+([\d.,]+)\s*$",
        text, re.MULTILINE,
    )
    if totals_line:
        # The last number in a multi-value totals line is often the total
        return _parse_amount(totals_line.group(4))

    return None


# ---------------------------------------------------------------------------
# Amount parsing (imported logic from invoice.py to avoid circular imports)
# ---------------------------------------------------------------------------

def _parse_amount(raw: str) -> float | None:
    """Parse a monetary amount: handles both European (1.234,56) and US (1234.56) formats."""
    raw = raw.strip()
    if not raw:
        return None
    # Must contain at least one digit
    if not re.search(r"\d", raw):
        return None
    # Handle negative
    neg = False
    if raw.startswith("-"):
        neg = True
        raw = raw[1:]
    # Strip trailing non-numeric chars (e.g. "$")
    raw = raw.rstrip("$ ")
    if not raw:
        return None
    try:
        # European: 1.234.567,89 -> remove dots, replace comma with dot
        if "," in raw and "." in raw:
            val = float(raw.replace(".", "").replace(",", "."))
        elif "," in raw:
            val = float(raw.replace(",", "."))
        elif "." in raw:
            parts = raw.split(".")
            if len(parts[-1]) == 3 and len(parts) > 1:
                val = float(raw.replace(".", ""))
            else:
                val = float(raw)
        else:
            val = float(raw)
    except ValueError:
        return None
    return -val if neg else val


def _clean_cuit(match: str) -> str:
    """Normalize CUIT to XX-XXXXXXXX-X format."""
    d = re.sub(r"[^\d]", "", match)
    if len(d) == 11:
        return f"{d[:2]}-{d[2:10]}-{d[10]}"
    return match
