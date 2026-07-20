"""Exportador JSON."""
from __future__ import annotations

import io
import json

from app.models.extraction import Extraction


def generate_json(ext: Extraction) -> io.BytesIO:
    buf = io.BytesIO()
    # Limpieza: asegurarnos de que los valores sean serializables
    data = _serialize(ext.data)
    buf.write(json.dumps(data, ensure_ascii=False, indent=2, default=str).encode("utf-8"))
    buf.seek(0)
    return buf


def _serialize(data: dict) -> dict:
    """Limpia el data para JSON."""
    clean: dict = {}
    for k, v in data.items():
        if isinstance(v, dict):
            clean[k] = _serialize(v)
        elif isinstance(v, list):
            clean[k] = [_serialize(i) if isinstance(i, dict) else i for i in v]
        else:
            clean[k] = v
    return clean
