"""Cliente OpenAI-compatible para extracción con LLM.

Soporta cualquier proveedor compatible con la API de OpenAI:
  OpenAI, OpenRouter, Ollama, Groq, etc.
Configuración vía OPENAI_BASE_URL + OPENAI_API_KEY + LLM_MODEL.
Soporta configuración por usuario (user.settings.llm).
"""
from __future__ import annotations

import json
import logging
from typing import Any

from openai import OpenAI

from app.config import settings

logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def get_client(user=None) -> OpenAI | None:
    """Devuelve un cliente OpenAI, o None si no hay API key.

    Si *user* tiene configuración LLM propia (user.settings.llm), se usa esa.
    En caso contrario se recurre a la configuración global.
    """
    # --- Configuración por usuario ---
    if user is not None:
        user_settings = getattr(user, "settings", None)
        if user_settings and isinstance(user_settings, dict):
            llm_cfg = user_settings.get("llm")
            if llm_cfg and isinstance(llm_cfg, dict):
                api_key = llm_cfg.get("api_key", "")
                base_url = llm_cfg.get("base_url", "")
                if api_key and base_url:
                    return OpenAI(
                        base_url=base_url,
                        api_key=api_key,
                        timeout=float(settings.llm_timeout),
                    )

    # --- Configuración global (singleton) ---
    global _client
    if not settings.llm_enabled:
        return None
    if _client is None:
        _client = OpenAI(
            base_url=settings.openai_base_url,
            api_key=settings.openai_api_key,
            timeout=float(settings.llm_timeout),
        )
    return _client


def _get_model_and_temperature(user=None) -> tuple[str, float]:
    """Devuelve (model, temperature) según la configuración del usuario o global."""
    if user is not None:
        user_settings = getattr(user, "settings", None)
        if user_settings and isinstance(user_settings, dict):
            llm_cfg = user_settings.get("llm")
            if llm_cfg and isinstance(llm_cfg, dict):
                model = llm_cfg.get("model") or settings.llm_model
                temperature = llm_cfg.get("temperature", settings.llm_temperature)
                return model, float(temperature)
    return settings.llm_model, float(settings.llm_temperature)


def extract_invoice_with_llm(text: str, client: OpenAI | None = None, user=None) -> dict[str, Any] | None:
    """Usa el LLM para extraer campos de factura con structured output."""
    client = client or get_client(user=user)
    if client is None:
        return None

    model, temperature = _get_model_and_temperature(user)

    system_prompt = """
Extraé campos de una factura argentina (AFIP tipo A/B/C) del siguiente texto.
Devolvé un JSON con las claves que encuentres. Dejá null las que no encuentres.
Claves posibles: invoice_number, point_of_sale, cuit, business_name, iva_condition,
emission_date, cae, cae_expiry, invoice_type, net, iva_amount, total, items.
Para "items", devolvelos como array de objetos con: description, quantity, unit_price, subtotal.
Solo devolvé el JSON, sin markdown ni backticks.
"""
    try:
        resp = client.chat.completions.create(
            model=model,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text[:8000]},  # truncar para no exceder contexto
            ],
        )
        content = resp.choices[0].message.content or ""
        # Intentar parsear JSON
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1]
        if content.endswith("```"):
            content = content.rsplit("```", 1)[0]
            content = content.strip()
        return json.loads(content)
    except (json.JSONDecodeError, IndexError, KeyError) as e:
        logger.warning("LLM extraction failed to parse: %s", e)
        return None
    except Exception as e:
        logger.error("LLM extraction error: %s", e)
        return None


def classify_with_llm(text: str, client: OpenAI | None = None, user=None) -> tuple[str, float] | None:
    """Usa el LLM para clasificar un documento. Devuelve (tipo, confianza) o None."""
    client = client or get_client(user=user)
    if client is None:
        return None

    model, _ = _get_model_and_temperature(user)

    types = "invoice, receipt, quote, contract, report, table, generic"
    system_prompt = f"""
Clasificá el siguiente texto de un documento en uno de estos tipos: {types}.
Devolvé SOLO un JSON con dos campos: "type" (el tipo) y "confidence" (0.0 a 1.0).
Sin markdown ni explicaciones.
"""
    try:
        resp = client.chat.completions.create(
            model=model,
            temperature=0.0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text[:4000]},
            ],
        )
        content = resp.choices[0].message.content.strip()
        data = json.loads(content.replace("```json", "").replace("```", "").strip())
        return data.get("type"), data.get("confidence", 0.5)
    except Exception as e:
        logger.warning("LLM classification error: %s", e)
        return None
