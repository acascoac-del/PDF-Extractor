"""Modelos ORM (SQLAlchemy).

Importar aquí todos los modelos para que Alembic y `Base.metadata` los vean.
"""
from app.models.user import User, Role
from app.models.api_token import ApiToken
from app.models.document import Document
from app.models.extraction import Extraction, FieldSource
from app.models.correction import Correction
from app.models.emitter_rule import EmitterRule

__all__ = [
    "User",
    "Role",
    "ApiToken",
    "Document",
    "Extraction",
    "FieldSource",
    "Correction",
    "EmitterRule",
]
