"""Servicio de aprendizaje automático de reglas por emisor.

Guarda reglas extraídas vía LLM o correcciones por CUIT de emisor,
y las re-aplica en futuras facturas del mismo emisor sin usar la IA.
"""
from __future__ import annotations

import logging
from typing import Any

try:
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from app.models.emitter_rule import EmitterRule
except ImportError:
    select = None
    Session = None
    EmitterRule = None

logger = logging.getLogger(__name__)


def get_learned_rule(db: Session, emitter_cuit: str, user_id: str | None = None) -> EmitterRule | None:
    """Busca una regla aprendida para un CUIT de emisor."""
    if not db or not emitter_cuit or select is None:
        return None

    cuit_clean = emitter_cuit.strip()
    query = select(EmitterRule).where(EmitterRule.emitter_cuit == cuit_clean)
    if user_id:
        query = query.where((EmitterRule.user_id == user_id) | (EmitterRule.user_id.is_(None)))

    query = query.order_by(EmitterRule.use_count.desc())
    return db.execute(query).scalars().first()


def save_learned_rule(
    db: Session,
    emitter_cuit: str,
    emitter_name: str | None,
    result_data: dict[str, Any],
    user_id: str | None = None,
) -> EmitterRule | None:
    """Guarda o actualiza la regla aprendida para un emisor."""
    if not db or not emitter_cuit:
        return None

    cuit_clean = emitter_cuit.strip()
    rule = get_learned_rule(db, cuit_clean, user_id=user_id)

    # Extraer firmas de estructura
    fields = result_data.get("fields", {})
    known_fields = {}
    for k, v in fields.items():
        if isinstance(v, dict) and v.get("value") is not None:
            known_fields[k] = {
                "source": v.get("source"),
                "confidence": v.get("confidence", 0.90),
            }

    rule_structure = {
        "emitter_name": emitter_name or (fields.get("emitter_name", {}).get("value") if isinstance(fields.get("emitter_name"), dict) else None),
        "known_fields": known_fields,
        "items_count": len(result_data.get("items", [])),
    }

    if rule is None:
        rule = EmitterRule(
            user_id=user_id,
            emitter_cuit=cuit_clean,
            emitter_name=emitter_name,
            rule_data=rule_structure,
            use_count=1,
        )
        db.add(rule)
    else:
        rule.use_count += 1
        rule.rule_data = rule_structure
        if emitter_name and not rule.emitter_name:
            rule.emitter_name = emitter_name

    try:
        db.commit()
        logger.info("Saved learned rule for emitter CUIT %s (use_count=%d)", cuit_clean, rule.use_count)
        return rule
    except Exception as e:
        logger.warning("Error saving learned rule for %s: %s", cuit_clean, e)
        db.rollback()
        return None
