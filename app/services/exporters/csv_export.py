"""Exportador CSV."""
from __future__ import annotations

import csv
import io

from app.models.extraction import Extraction


def generate_csv(ext: Extraction) -> io.StringIO:
    buf = io.StringIO()
    fields = ext.data.get("fields", {})
    items = ext.data.get("items", [])

    writer = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_ALL)

    # Encabezado: campos
    writer.writerow(["Campo", "Valor", "Confianza", "Fuente"])
    for key, f in fields.items():
        writer.writerow([key, f.get("value", ""), f.get("confidence", ""), f.get("source", "")])

    # Items
    if items:
        writer.writerow([])
        writer.writerow(["# Item", "Descripción", "Cantidad", "Precio Unit.", "Subtotal"])
        for i, item in enumerate(items, 1):
            writer.writerow([
                i,
                item.get("description", ""),
                item.get("quantity", ""),
                item.get("unit_price", ""),
                item.get("subtotal", ""),
            ])

    buf.seek(0)
    return buf
