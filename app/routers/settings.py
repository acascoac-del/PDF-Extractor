"""Router de configuración de usuario (proveedor IA, API key, modelo).

Endpoints:
  GET  /app/settings            - Página de configuración
  POST /app/settings/llm        - Guardar configuración LLM
  GET  /app/settings/fetch-models - Obtener modelos disponibles del proveedor
"""
from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.deps import get_current_user_optional, get_db
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/app/settings")
templates = Jinja2Templates(directory="app/templates")

from app.services.llm import PROVIDER_URLS

PROVIDER_LABELS = {
    "groq": "Groq",
    "openrouter": "OpenRouter",
    "openai": "OpenAI",
    "ollama": "Ollama (Local)",
    "custom": "Personalizado",
}


# ---------- Página de configuración ----------

@router.get("")
def settings_page(
    request: Request,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    if user is None:
        return RedirectResponse("/auth/login", status_code=303)

    # Extraer settings LLM actuales del usuario
    llm_settings = {}
    if user.settings and isinstance(user.settings, dict):
        llm_settings = user.settings.get("llm", {})

    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "user": user,
            "section": "settings",
            "llm": llm_settings,
            "providers": PROVIDER_LABELS,
            "provider_urls": PROVIDER_URLS,
        },
    )


# ---------- Guardar configuración LLM ----------

@router.post("/llm")
def save_llm_settings(
    request: Request,
    provider: str = Form(...),
    api_key: str = Form(""),
    base_url: str = Form(""),
    model: str = Form(""),
    temperature: float = Form(0.0),
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    # Verificar autenticación manualmente para soportar POST con form
    if user is None:
        token = request.cookies.get("access_token", "")
        if token:
            from app.auth.security import decode_token
            if token.lower().startswith("bearer "):
                token = token[7:]
            payload = decode_token(token)
            if payload and payload.get("type") == "access":
                user = db.get(User, payload.get("sub"))
                if user and not user.is_active:
                    user = None

    if user is None:
        return RedirectResponse("/auth/login", status_code=303)

    # Si no se proporciona base_url, autocompletar con la URL base del proveedor seleccionado
    if not base_url and provider in PROVIDER_URLS:
        base_url = PROVIDER_URLS[provider]

    DEFAULT_MODELS = {
        "groq": "llama-3.3-70b-versatile",
        "openrouter": "qwen/qwen-2.5-72b-instruct",
        "openai": "gpt-4o-mini",
        "ollama": "llama3.2",
    }

    if not model or (provider == "groq" and model in ("gpt-4o-mini", "llama3-70b-8192", "llama3-8b-8192")) or (provider == "openrouter" and model in ("gpt-4o-mini", "qwen")):
        model = DEFAULT_MODELS.get(provider, "gpt-4o-mini")

    # Construir el objeto settings
    from sqlalchemy.orm.attributes import flag_modified
    current_settings = dict(user.settings) if user.settings and isinstance(user.settings, dict) else {}
    current_settings["llm"] = {
        "provider": provider,
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
        "temperature": temperature,
    }
    user.settings = current_settings
    flag_modified(user, "settings")
    db.commit()
    db.refresh(user)

    # Re-render con mensaje de éxito
    llm_settings = user.settings.get("llm", {})
    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "user": user,
            "section": "settings",
            "llm": llm_settings,
            "providers": PROVIDER_LABELS,
            "provider_urls": PROVIDER_URLS,
            "success": "Configuración guardada correctamente.",
        },
    )


# ---------- Obtener modelos disponibles ----------

@router.get("/fetch-models")
async def fetch_models(
    provider: str = Query(...),
    api_key: str = Query(""),
    base_url: str = Query(""),
    user: User | None = Depends(get_current_user_optional),
):
    # Si no se proporciona base_url, usar el preset del proveedor
    if not base_url:
        base_url = PROVIDER_URLS.get(provider, "")

    if not base_url:
        return JSONResponse(
            {"error": "URL base no configurada para este proveedor."},
            status_code=400,
        )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            if provider == "ollama":
                # Ollama usa un endpoint diferente: /api/tags
                ollama_base = base_url.replace("/v1", "").rstrip("/")
                resp = await client.get(f"{ollama_base}/api/tags")
                resp.raise_for_status()
                data = resp.json()
                models = [
                    {"id": m.get("name", ""), "name": m.get("name", "")}
                    for m in data.get("models", [])
                ]
            else:
                # Formato OpenAI-compatible: GET /models
                headers = {}
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"
                resp = await client.get(f"{base_url.rstrip('/')}/models", headers=headers)
                resp.raise_for_status()
                data = resp.json()
                raw_models = data.get("data", [])
                models = [
                    {"id": m.get("id", ""), "name": m.get("id", "")}
                    for m in raw_models
                ]

        models.sort(key=lambda x: x["id"].lower())
        return JSONResponse({"models": models})

    except httpx.HTTPStatusError as e:
        logger.warning("HTTP error fetching models from %s: %s", provider, e)
        return JSONResponse(
            {"error": f"Error del proveedor (HTTP {e.response.status_code}). Verificá tu API key."},
            status_code=e.response.status_code,
        )
    except httpx.TimeoutException:
        logger.warning("Timeout fetching models from %s", provider)
        return JSONResponse(
            {"error": "El proveedor tardó demasiado en responder (timeout)."},
            status_code=504,
        )
    except httpx.ConnectError:
        logger.warning("Connection error fetching models from %s", provider)
        if provider == "ollama":
            return JSONResponse(
                {"error": "No se pudo conectar a Ollama. ¿Está ejecutándose en localhost:11434?"},
                status_code=502,
            )
        return JSONResponse(
            {"error": "No se pudo conectar al proveedor. Verificá la URL base."},
            status_code=502,
        )
    except Exception as e:
        logger.error("Unexpected error fetching models: %s", e)
        return JSONResponse(
            {"error": f"Error inesperado: {str(e)}"},
            status_code=500,
        )
