"""Servicio de almacenamiento: guarda PDFs en disco fuera del webroot."""
from __future__ import annotations

import secrets
from pathlib import Path

from app.config import settings


def _ext(filename: str) -> str:
    return Path(filename).suffix.lower()


def save_upload(content: bytes, original_filename: str) -> tuple[str, str]:
    """Persiste el archivo y devuelve (stored_filename, abs_path)."""
    ext = _ext(original_filename) or ".pdf"
    # nombre aleatorio para evitar colisiones y path traversal
    stored = f"{secrets.token_hex(16)}{ext}"
    abs_path = Path(settings.upload_dir) / stored
    abs_path.write_bytes(content)
    # Guardamos relativo a STORAGE_DIR para portabilidad entre entornos.
    rel = f"uploads/{stored}"
    return stored, rel


def abs_path_for(rel: str) -> Path:
    """Convierte ruta relativa (uploads/abc.pdf) a absoluta."""
    return Path(settings.storage_dir) / rel


def delete_file(rel: str | None) -> None:
    if not rel:
        return
    try:
        p = abs_path_for(rel)
        if p.exists():
            p.unlink()
    except OSError:
        pass
