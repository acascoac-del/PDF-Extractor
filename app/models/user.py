"""Modelo de usuario y roles."""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, String, func
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _uuid_str() -> str:
    return str(uuid.uuid4())


class Role(str, enum.Enum):
    """Roles disponibles."""

    ADMIN = "admin"
    USER = "user"


class User(Base):
    """Usuario de la aplicación."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), default="")
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.USER, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    settings: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)

    # --- Suscripción / Plan ---
    plan: Mapped[str] = mapped_column(String(16), default="free", nullable=False)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    subscription_status: Mapped[str] = mapped_column(String(16), default="none", nullable=False)
    subscription_end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pdf_count_month: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pdf_count_reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<User {self.username} ({self.role.value})>"
