"""Cálculo de confianza por campo y global."""
from __future__ import annotations

from typing import Any


def compute_overall_confidence(data: dict[str, Any]) -> float:
    """Promedia la confianza de todos los campos con valor no-nulo."""
    fields = data.get("fields", {})
    scores = []
    for key, val in fields.items():
        if val.get("value") is not None and val["value"] != "":
            scores.append(val.get("confidence", 0.0))
    if not scores:
        return 0.0
    return round(sum(scores) / len(scores), 3)


def confidence_class(score: float | None) -> str:
    """Devuelve la clase CSS para el badge de confianza."""
    if score is None:
        return ""
    if score >= 0.8:
        return "conf-high"
    if score >= 0.5:
        return "conf-medium"
    return "conf-low"


def confidence_label(score: float | None) -> str:
    """Etiqueta legible."""
    if score is None:
        return "?"
    if score >= 0.8:
        return "Alta"
    if score >= 0.5:
        return "Media"
    return "Baja"
