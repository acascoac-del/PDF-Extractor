"""Tokens de API para integraciones externas (REST)."""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _uuid_str() -> str:
    return str(uuid.uuid4())


def _generate_token() -> str:
    """Prefijo legible + parte secreta. Ej: pe_live_<32 hex>."""
    return "pe_" + secrets.token_hex(24)


class ApiToken(Base):
    """Token de larga duración para acceder a la API REST sin JWT."""

    __tablename__ = "api_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # El token se guarda hasheado (SHA-256) — el valor plano solo se muestra una vez.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), default="default")
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User")  # noqa: F821

    def __repr__(self) -> str:
        return f"<ApiToken {self.name} user={self.user_id}>"
