"""Bootstrap: crea el usuario admin inicial si está configurado.

Se ejecuta una sola vez al arranque (idempotente).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models.user import Role, User
from app.auth.security import hash_password


def ensure_initial_admin() -> None:
    db: Session = SessionLocal()
    try:
        email = settings.initial_admin_email.strip().lower()
        username = settings.initial_admin_username.strip().lower()
        existing = (
            db.query(User).filter((User.email == email) | (User.username == username)).first()
        )
        if existing:
            return
        admin = User(
            email=email,
            username=username,
            full_name="Administrador",
            hashed_password=hash_password(settings.initial_admin_password),
            role=Role.ADMIN,
            is_active=True,
        )
        db.add(admin)
        db.commit()
    finally:
        db.close()
