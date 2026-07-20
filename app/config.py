"""Configuración central de la aplicación (pydantic-settings).

Las variables se cargan desde el entorno o un archivo .env.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


# Rutas base (absolutas, para Docker y local)
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Configuración global. Lee de entorno / .env automáticamente."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- App ---
    app_name: str = "PDF Extractor"
    app_url: str = ""  # https://tu-app.vercel.app (para webhooks y redirecciones)
    environment: str = "development"
    secret_key: str = "cambia-esta-clave-por-una-larga-y-aleatoria"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 días
    timezone: str = "America/Argentina/Buenos_Aires"

    # --- Base de datos ---
    database_url: str = "sqlite:///./storage/app.db"

    # --- Redis / Celery (opcional, no necesario en Vercel) ---
    redis_url: str = ""
    celery_broker_url: str = ""
    celery_result_backend: str = ""

    # --- LLM (OpenAI-compatible) ---
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.0
    llm_timeout: int = 60

    # --- OCR ---
    tesseract_cmd: str = ""
    ocr_languages: str = "spa+eng"
    ocr_dpi: int = 300

    # --- Almacenamiento local (desarrollo) ---
    storage_dir: str = str(BASE_DIR / "storage")
    upload_dir: str = str(BASE_DIR / "storage" / "uploads")
    processed_dir: str = str(BASE_DIR / "storage" / "processed")
    exports_dir: str = str(BASE_DIR / "storage" / "exports")
    max_upload_mb: int = 30

    # --- Cloudflare R2 (produccion / Vercel) ---
    r2_endpoint_url: str = ""  # https://xxx.r2.cloudflarestorage.com
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = "pdf-extractor"
    r2_public_url: str = ""  # https://pub-xxx.r2.dev (opcional, para acceso publico)

    # --- Mercado Pago ---
    mp_access_token: str = ""
    mp_public_key: str = ""
    mp_webhook_secret: str = ""
    mp_plan_id: str = ""  # Plan ID de Mercado Pago

    # --- Stripe (legacy, mantener para compatibilidad) ---
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    stripe_price_id: str = ""
    stripe_webhook_secret: str = ""

    # --- Seguridad / retención ---
    auto_delete_days: int = 30
    cleanup_cron_hour: int = 3

    # --- Admin inicial ---
    initial_admin_email: str = ""
    initial_admin_username: str = "admin"
    initial_admin_password: str = ""

    # --- Propiedades derivadas ---
    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_postgres(self) -> bool:
        return not self.is_sqlite

    @property
    def llm_enabled(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def r2_enabled(self) -> bool:
        return bool(self.r2_access_key_id and self.r2_endpoint_url)

    @property
    def celery_enabled(self) -> bool:
        return bool(self.celery_broker_url)

    @property
    def mp_enabled(self) -> bool:
        return bool(self.mp_access_token)

    def ensure_dirs(self) -> None:
        """Crea los directorios de almacenamiento si no existen."""
        if not self.r2_enabled:
            for d in (self.storage_dir, self.upload_dir, self.processed_dir, self.exports_dir):
                Path(d).mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Instancia única de Settings (cacheada)."""
    s = Settings()
    s.ensure_dirs()
    return s


settings = get_settings()
