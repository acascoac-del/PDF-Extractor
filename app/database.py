"""Configuración de la base de datos con SQLAlchemy 2.x.

SQLite por defecto, fácilmente migrable a Postgres cambiando DATABASE_URL.
"""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


# SQLite necesita argumentos extra para permitir uso desde múltiples threads
# (Celery worker + web app comparten la misma DB en desarrollo).
_connect_args: dict = {}
if settings.is_sqlite:
    _connect_args = {"check_same_thread": False, "timeout": 30}

engine = create_engine(
    settings.database_url,
    connect_args=_connect_args,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    class_=Session,
    future=True,
)


class Base(DeclarativeBase):
    """Clase base para todos los modelos ORM."""


def get_db() -> Generator[Session, None, None]:
    """Dependencia de FastAPI: abre y cierra una sesión por request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Crea todas las tablas (útil para primer arranque sin Alembic).

    En producción debe usarse Alembic; esta función es un atajo de dev.
    """
    # Importar todos los modelos para que SQLAlchemy los registre.
    from app.models import document, user  # noqa: F401

    Base.metadata.create_all(bind=engine)
