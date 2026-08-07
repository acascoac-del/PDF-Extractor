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

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # type: ignore

from app.config import settings

logger = logging.getLogger(__name__)

_client = None


PROVIDER_URLS = {
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "openai": "https://api.openai.com/v1",
    "ollama": "http://localhost:11434/v1",
    "custom": "",
}

DEFAULT_PROVIDER_MODELS = {
    "groq": "llama-3.3-70b-versatile",
    "openrouter": "qwen/qwen-2.5-72b-instruct",
    "openai": "gpt-4o-mini",
    "ollama": "llama3.2",
}

DEPRECATED_GROQ_MODELS = {
    "llama3-70b-8192": "llama-3.3-70b-versatile",
    "llama3-8b-8192": "llama-3.1-8b-instant",
    "mixtral-8x7b-32768": "llama-3.3-70b-versatile",
    "gpt-4o-mini": "llama-3.3-70b-versatile",
}

INVALID_OPENROUTER_MODELS = {
    "gpt-4o-mini": "qwen/qwen-2.5-72b-instruct",
    "qwen": "qwen/qwen-2.5-72b-instruct",
    "llama3": "meta-llama/llama-3.3-70b-instruct",
}


def get_client(user=None):
    """Devuelve un cliente OpenAI, o None si no hay API key o librería openai."""
    if OpenAI is None:
        return None

    # --- Configuración por usuario ---
    if user is not None:
        user_settings = getattr(user, "settings", None)
        if user_settings and isinstance(user_settings, dict):
            llm_cfg = user_settings.get("llm")
            if llm_cfg and isinstance(llm_cfg, dict):
                provider = llm_cfg.get("provider", "openai")
                api_key = (llm_cfg.get("api_key") or "").strip()
                base_url = (llm_cfg.get("base_url") or "").strip()
                model = (llm_cfg.get("model") or "").strip()
                temperature = float(llm_cfg.get("temperature", settings.llm_temperature))

                if not base_url:
                    base_url = PROVIDER_URLS.get(provider, "")

                if not api_key and provider == "ollama":
                    api_key = "ollama"

                # Ajustar modelo por defecto si no es válido para el proveedor
                if not model or (provider == "groq" and model in DEPRECATED_GROQ_MODELS):
                    model = DEPRECATED_GROQ_MODELS.get(model) or DEFAULT_PROVIDER_MODELS.get(provider, settings.llm_model)
                elif provider == "openrouter" and (not model or model in INVALID_OPENROUTER_MODELS):
                    model = INVALID_OPENROUTER_MODELS.get(model) or DEFAULT_PROVIDER_MODELS.get(provider, settings.llm_model)

                if base_url:
                    client_kwargs = {
                        "base_url": base_url,
                        "api_key": api_key or "none",
                        "timeout": float(settings.llm_timeout),
                    }
                    if provider == "openrouter" or "openrouter" in base_url.lower():
                        client_kwargs["default_headers"] = {
                            "HTTP-Referer": "https://pdf-extractor.app",
                            "X-Title": "PDF Extractor",
                        }

                    client = OpenAI(**client_kwargs)
                    setattr(client, "provider", provider)
                    setattr(client, "model", model)
                    setattr(client, "temperature", temperature)
                    return client

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
    setattr(_client, "provider", "global")
    setattr(_client, "model", settings.llm_model)
    setattr(_client, "temperature", float(settings.llm_temperature))
    return _client


def _get_model_and_temperature(user=None, client: OpenAI | None = None) -> tuple[str, float]:
    """Devuelve (model, temperature) priorizando el cliente, luego la configuración del usuario y finalmente la global."""
    if client is not None:
        model = getattr(client, "model", None)
        temperature = getattr(client, "temperature", None)
        provider = getattr(client, "provider", "")
        if model:
            if provider == "groq" and model in DEPRECATED_GROQ_MODELS:
                model = DEPRECATED_GROQ_MODELS[model]
            elif provider == "openrouter" and model in INVALID_OPENROUTER_MODELS:
                model = INVALID_OPENROUTER_MODELS[model]
            return model, float(temperature if temperature is not None else settings.llm_temperature)

    if user is not None:
        user_settings = getattr(user, "settings", None)
        if user_settings and isinstance(user_settings, dict):
            llm_cfg = user_settings.get("llm")
            if llm_cfg and isinstance(llm_cfg, dict):
                provider = llm_cfg.get("provider", "openai")
                model = llm_cfg.get("model") or DEFAULT_PROVIDER_MODELS.get(provider, settings.llm_model)
                if provider == "groq" and model in DEPRECATED_GROQ_MODELS:
                    model = DEPRECATED_GROQ_MODELS[model]
                elif provider == "openrouter" and model in INVALID_OPENROUTER_MODELS:
                    model = INVALID_OPENROUTER_MODELS[model]
                temperature = llm_cfg.get("temperature", settings.llm_temperature)
                return model, float(temperature)

    return settings.llm_model, float(settings.llm_temperature)


import re


def clean_json_response(content: str | None) -> Any | None:
    """Extrae y parsea JSON de una respuesta de LLM de forma robusta.

    Soporta:
    - Respuestas limpias con JSON.
    - Bloques markdown (```json ... ``` o ``` ... ```).
    - Modelos con etiquetas de pensamiento (<think>...</think>, <thinking>...</thinking>, etc.),
      incluso si la etiqueta no fue cerrada debido a truncamiento.
    - Texto explicativo antes/después del objeto JSON.
    """
    if not content or not isinstance(content, str):
        return None

    text = content.strip()

    # 1. Eliminar etiquetas de pensamiento cerradas: <think>...</think>, <thinking>...</thinking>, <reasoning>...</reasoning>
    text = re.sub(r"<(think|thinking|reasoning)>.*?</\1>", "", text, flags=re.DOTALL | re.IGNORECASE).strip()

    # 2. Manejar etiquetas de pensamiento sin cerrar (unclosed <think> por truncamiento de tokens)
    for tag in ["think", "thinking", "reasoning"]:
        tag_pattern = re.compile(rf"<{tag}>", re.IGNORECASE)
        match = tag_pattern.search(text)
        if match:
            after_tag = text[match.end():]
            json_match = re.search(r"[{\[]", after_tag)
            if json_match:
                text = after_tag[json_match.start():]
            else:
                text = text[:match.start()]
            text = text.strip()

    # 3. Si hay bloques markdown ```json ... ``` o ``` ... ```, extraer contenido del bloque
    match_code = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, flags=re.DOTALL | re.IGNORECASE)
    if match_code:
        text = match_code.group(1).strip()

    # 4. Intentar parsear directamente
    try:
        res = json.loads(text)
        if isinstance(res, (dict, list)):
            return res
    except json.JSONDecodeError:
        pass

    # 5. Intentar extraer desde el primer '{' o '[' al último '}' o ']'
    start_brace = text.find("{")
    start_bracket = text.find("[")

    start_pos = -1
    end_pos = -1

    if start_brace != -1 and (start_bracket == -1 or start_brace < start_bracket):
        start_pos = start_brace
        end_pos = text.rfind("}")
    elif start_bracket != -1:
        start_pos = start_bracket
        end_pos = text.rfind("]")

    if start_pos != -1 and end_pos != -1 and end_pos > start_pos:
        json_str = text[start_pos : end_pos + 1].strip()
        try:
            res = json.loads(json_str)
            if isinstance(res, (dict, list)):
                return res
        except json.JSONDecodeError:
            cleaned = re.sub(r",\s*([}\]])", r"\1", json_str)
            try:
                res = json.loads(cleaned)
                if isinstance(res, (dict, list)):
                    return res
            except json.JSONDecodeError:
                pass

    return None


def extract_invoice_with_llm(text: str, client: OpenAI | None = None, user=None) -> dict[str, Any] | None:
    """Usa el LLM para extraer campos de factura con structured output."""
    client = client or get_client(user=user)
    if client is None:
        return None

    model, temperature = _get_model_and_temperature(user=user, client=client)

    system_prompt = """
Extraé campos de una factura argentina (AFIP tipo A/B/C) del siguiente texto.
Devolvé un JSON con las claves que encuentres. Dejá null las que no encuentres.
Claves posibles:
- Encabezado: invoice_number, point_of_sale, cuit, emitter_name, emitter_cuit, receptor_name, receptor_cuit, business_name, iva_condition, emission_date, cae, cae_expiry, invoice_type
- Totales y Resumen: subtotal, net (neto gravado), iva_amount (IVA), iibb (IIBB / Ingresos Brutos), tasas_municipales, sellos, percepcion_iva, itc (ITC), co2 (CO2), icl_amount, idc_amount, financiacion, tasa_vial, total
- Items: array de objetos con description, quantity, unit_price, subtotal (o import).
- summary_breakdown: array de objetos con cada fila del cuadro resumen de la factura (cada objeto con: label, amount) (ej: Subtotal, IVA, IIBB, Tasas municipales, Sellos, Percep. IVA, ITC, CO2, Total en Pesos).

Responde ÚNICAMENTE con el objeto JSON válido dentro de un bloque ```json ... ```. Sin explicaciones fuera del JSON.
"""
    provider = getattr(client, "provider", "")
    if provider == "groq" or "groq" in str(getattr(client, "base_url", "")).lower():
        max_tokens = 2048
        text_limit = 6000
    else:
        max_tokens = 4096
        text_limit = 10000

    if "deepseek-r1" in model.lower():
        temperature = max(temperature, 0.6)

    try:
        kwargs = {
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text[:text_limit]},
            ],
        }
        try:
            resp = client.chat.completions.create(
                **kwargs,
                response_format={"type": "json_object"},
            )
        except Exception:
            resp = client.chat.completions.create(**kwargs)

        content = resp.choices[0].message.content or ""
        parsed = clean_json_response(content)
        if isinstance(parsed, dict):
            return parsed
        logger.warning("LLM extraction failed to parse JSON from content: %r", content[:200])
        return None
    except Exception as e:
        logger.error("LLM extraction error: %s", e)
        return None


def classify_with_llm(text: str, client: OpenAI | None = None, user=None) -> tuple[str, float] | None:
    """Usa el LLM para clasificar un documento. Devuelve (tipo, confianza) o None."""
    client = client or get_client(user=user)
    if client is None:
        return None

    model, _ = _get_model_and_temperature(user=user, client=client)

    types = "invoice, receipt, quote, contract, report, table, generic"
    system_prompt = f"""
Clasificá el siguiente texto de un documento en uno de estos tipos: {types}.
Devolvé SOLO un JSON con dos campos: "type" (el tipo) y "confidence" (0.0 a 1.0).
Sin markdown ni explicaciones.
"""
    try:
        kwargs = {
            "model": model,
            "temperature": 0.0,
            "max_tokens": 1024,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text[:4000]},
            ],
        }
        try:
            resp = client.chat.completions.create(
                **kwargs,
                response_format={"type": "json_object"},
            )
        except Exception:
            resp = client.chat.completions.create(**kwargs)

        content = resp.choices[0].message.content or ""
        data = clean_json_response(content)
        if isinstance(data, dict):
            return data.get("type"), data.get("confidence", 0.5)
        return None
    except Exception as e:
        logger.warning("LLM classification error: %s", e)
        return None

