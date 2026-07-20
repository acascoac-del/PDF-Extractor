"""Exportador ZIP en lote: empaqueta xlsx + docx + csv + json."""
from __future__ import annotations

import io
import zipfile

from app.models.document import Document
from app.models.extraction import Extraction
from app.services.exporters.excel import generate_excel
from app.services.exporters.word import generate_word
from app.services.exporters.csv_export import generate_csv
from app.services.exporters.json_export import generate_json


def generate_batch_zip(doc: Document, ext: Extraction) -> io.BytesIO:
    buf = io.BytesIO()

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        stem = doc.original_filename.rsplit(".", 1)[0]
        safe = "".join(c for c in stem[:60] if c.isalnum() or c in " -_")

        # Excel
        xlsx_buf = generate_excel(doc, ext)
        zf.writestr(f"{safe}.xlsx", xlsx_buf.getvalue())

        # Word
        docx_buf = generate_word(doc, ext)
        zf.writestr(f"{safe}.docx", docx_buf.getvalue())

        # CSV
        csv_buf = generate_csv(ext)
        zf.writestr(f"{safe}.csv", csv_buf.getvalue().encode("utf-8"))

        # JSON
        json_buf = generate_json(ext)
        zf.writestr(f"{safe}.json", json_buf.getvalue())

    buf.seek(0)
    return buf
