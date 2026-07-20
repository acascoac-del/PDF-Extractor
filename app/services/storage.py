"""Servicio de almacenamiento: guarda PDFs en R2 (produccion) o disco (desarrollo).

Cuando R2 esta configurado (r2_access_key_id + r2_endpoint_url), usa Cloudflare R2.
Si no, cae en almacenamiento local.
"""
from __future__ import annotations

import secrets
from pathlib import Path

from app.config import settings


def _ext(filename: str) -> str:
    return Path(filename).suffix.lower()


def save_upload(content: bytes, original_filename: str) -> tuple[str, str]:
    """Persiste el archivo y devuelve (stored_name, rel_path).

    - En R2: rel_path es la key dentro del bucket (uploads/xxx.pdf).
    - En local: rel_path es relativo a storage_dir (uploads/xxx.pdf).
    """
    ext = _ext(original_filename) or ".pdf"
    stored = f"{secrets.token_hex(16)}{ext}"

    if settings.r2_enabled:
        from app.services.r2_storage import upload_file

        key = upload_file(content, original_filename, content_type="application/pdf")
        # stored_name es el nombre del archivo, rel_path es la key completa de R2
        return stored, key
    else:
        abs_path = Path(settings.upload_dir) / stored
        abs_path.write_bytes(content)
        rel = f"uploads/{stored}"
        return stored, rel


def abs_path_for(rel: str) -> Path | None:
    """Convierte ruta relativa a absoluta (solo para almacenamiento local).

    Devuelve None si se usa R2 (usar read_file en su lugar).
    """
    if settings.r2_enabled:
        return None
    return Path(settings.storage_dir) / rel


def read_file(rel: str) -> bytes:
    """Lee un archivo desde R2 o almacenamiento local."""
    if settings.r2_enabled:
        from app.services.r2_storage import download_file

        return download_file(rel)
    else:
        p = abs_path_for(rel)
        if p is None or not p.exists():
            raise FileNotFoundError(f"Archivo no encontrado: {rel}")
        return p.read_bytes()


def delete_file(rel: str | None) -> None:
    if not rel:
        return
    try:
        if settings.r2_enabled:
            from app.services.r2_storage import delete_file as r2_delete

            r2_delete(rel)
        else:
            p = abs_path_for(rel)
            if p and p.exists():
                p.unlink()
    except Exception:
        pass


def file_exists(rel: str) -> bool:
    """Verifica si un archivo existe."""
    if settings.r2_enabled:
        # En R2, intentamos descargar para verificar existencia
        try:
            from app.services.r2_storage import _get_r2_client

            client = _get_r2_client()
            client.head_object(Bucket=settings.r2_bucket_name, Key=rel)
            return True
        except Exception:
            return False
    else:
        p = abs_path_for(rel)
        return p is not None and p.exists()
