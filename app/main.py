"""Aplicación FastAPI principal.

En esta primera iteración expone un health-check y crea las tablas al arranque.
Las siguientes fases agregan routers (auth, documents, exports, api).
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import __version__
from app.auth.router import router as auth_api_router
from app.config import settings
from app.routers.pages import router as pages_router
from app.routers.documents import router as documents_router
from app.routers.exports import router as exports_router
from app.routers.api import router as api_router
from app.routers.settings import router as settings_router
from app.routers.subscription import router as subscription_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Arranque: asegura directorios, crea tablas y admin inicial."""
    settings.ensure_dirs()
    # Crea tablas (en dev; en prod se usa Alembic).
    from app.database import init_db

    init_db()

    # Crea admin inicial si está configurado.
    if settings.initial_admin_email and settings.initial_admin_password:
        from app.auth.bootstrap import ensure_initial_admin

        ensure_initial_admin()

    yield


app = FastAPI(
    title=settings.app_name,
    version=__version__,
    description="Conversor inteligente de PDF a Excel/Word con extracción estructurada.",
    lifespan=lifespan,
)

# Archivos estáticos y plantillas
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# Routers
app.include_router(pages_router)
app.include_router(auth_api_router)
app.include_router(documents_router)
app.include_router(exports_router)
app.include_router(api_router)
app.include_router(settings_router)
app.include_router(subscription_router)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": __version__,
        "environment": settings.environment,
        "llm_enabled": settings.llm_enabled,
    }
