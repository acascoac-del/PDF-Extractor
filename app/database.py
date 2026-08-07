"""Configuración de la base de datos con SQLAlchemy 2.x.

SQLite por defecto, PostgreSQL via DATABASE_URL (Neon, etc.).
Para Vercel serverless: pool adaptado a conexiones efímeras.
"""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


# Argumentos de conexion segun el motor de base de datos
_connect_args: dict = {}
_engine_kwargs: dict = {
    "pool_pre_ping": True,
    "future": True,
}

if settings.is_sqlite:
    # SQLite necesita argumentos extra para permitir uso desde múltiples threads
    _connect_args = {"check_same_thread": False, "timeout": 30}
else:
    # PostgreSQL (Neon / Vercel): pool reducido para serverless
    _engine_kwargs.update({
        "pool_size": 5,
        "max_overflow": 0,
        "pool_recycle": 300,  # Reciclar conexiones cada 5 min
        "pool_timeout": 10,
    })

engine = create_engine(
    settings.database_url,
    connect_args=_connect_args,
    **_engine_kwargs,
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
    # Importar todos los modelos para que SQLAlchemy los registre en metadata.
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
