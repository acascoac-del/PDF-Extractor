"""Interfaz base para extractores."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExtractionResult:
    data: dict[str, Any] = field(default_factory=dict)
    llm_model: str | None = None

    def set_field(self, key: str, value: Any, source: str, confidence: float, raw: Any = None) -> None:
        """Helper para poblar el dict data con metadata de confianza."""
        if "fields" not in self.data:
            self.data["fields"] = {}
        self.data["fields"][key] = {
            "value": value,
            "source": source,
            "confidence": confidence,
            "raw": raw if raw is not None else value,
        }

    def add_items(self, items: list[dict]) -> None:
        if "items" not in self.data:
            self.data["items"] = []
        self.data["items"].extend(items)

    def set_meta(self, key: str, value: Any) -> None:
        if "meta" not in self.data:
            self.data["meta"] = {}
        self.data["meta"][key] = value
