"""Servicio de almacenamiento Cloudflare R2 (compatible con S3).

R2 se usa en producción (Vercel) donde no hay sistema de archivos persistente.
En desarrollo, el fallback es almacenamiento local.
"""
from __future__ import annotations

import uuid

from app.config import settings


def _get_r2_client():
    """Crea un cliente boto3 para R2 (lazy import para no requerir boto3 en dev)."""
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=settings.r2_endpoint_url,
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        region_name="auto",
    )


def upload_file(content: bytes, filename: str, content_type: str = "application/pdf") -> str:
    """Sube un archivo a R2 y devuelve la key (ruta dentro del bucket)."""
    ext = filename.rsplit(".", 1)[-1] if "." in filename else "pdf"
    key = f"uploads/{uuid.uuid4().hex}.{ext}"
    client = _get_r2_client()
    client.put_object(
        Bucket=settings.r2_bucket_name,
        Key=key,
        Body=content,
        ContentType=content_type,
    )
    return key


def download_file(key: str) -> bytes:
    """Descarga un archivo de R2."""
    client = _get_r2_client()
    response = client.get_object(Bucket=settings.r2_bucket_name, Key=key)
    return response["Body"].read()


def delete_file(key: str) -> None:
    """Elimina un archivo de R2."""
    client = _get_r2_client()
    client.delete_object(Bucket=settings.r2_bucket_name, Key=key)


def get_presigned_url(key: str, expires_in: int = 3600) -> str:
    """Genera una URL pre-firmada para descarga temporal."""
    client = _get_r2_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.r2_bucket_name, "Key": key},
        ExpiresIn=expires_in,
    )


def get_public_url(key: str) -> str:
    """Devuelve la URL pública directa si está configurado r2_public_url."""
    if settings.r2_public_url:
        return f"{settings.r2_public_url.rstrip('/')}/{key}"
    return get_presigned_url(key)
