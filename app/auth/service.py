"""Servicio de autenticación: registro, login, gestión de usuarios y API tokens."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import create_access_token, hash_password, verify_password
from app.models.api_token import ApiToken, _generate_token
from app.models.user import Role, User
from app.schemas.auth import UserCreate


class AuthError(Exception):
    """Error de negocio de autenticación."""

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _hash_api_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


# ---------- Registro / login ----------

def register_user(db: Session, data: UserCreate) -> User:
    email = data.email.strip().lower()
    username = data.username.strip().lower()
    existing = db.execute(
        select(User).where((User.email == email) | (User.username == username))
    ).scalar_one_or_none()
    if existing:
        if existing.email == email:
            raise AuthError("Ya existe un usuario con ese email.", 409)
        raise AuthError("Ya existe un usuario con ese nombre de usuario.", 409)
    # El primer usuario es admin; los demás, user común.
    is_first = db.execute(select(User)).first() is None
    user = User(
        email=email,
        username=username,
        full_name=data.full_name.strip(),
        hashed_password=hash_password(data.password),
        role=Role.ADMIN if is_first else Role.USER,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate(db: Session, login: str, password: str) -> Optional[User]:
    """Acepta username o email."""
    login = login.strip().lower()
    stmt = select(User).where((User.username == login) | (User.email == login))
    user = db.execute(stmt).scalar_one_or_none()
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def login_user(db: Session, username: str, password: str) -> tuple[User, str]:
    user = authenticate(db, username, password)
    if user is None:
        raise AuthError("Usuario o contraseña incorrectos.", 401)
    token = create_access_token(subject=user.id, extra={"role": user.role.value})
    return user, token


# ---------- API tokens ----------

def create_api_token(db: Session, user: User, name: str) -> tuple[ApiToken, str]:
    raw = _generate_token()
    token = ApiToken(
        user_id=user.id,
        token_hash=_hash_api_token(raw),
        name=name or "default",
    )
    db.add(token)
    db.commit()
    db.refresh(token)
    return token, raw


def list_api_tokens(db: Session, user: User) -> list[ApiToken]:
    return list(
        db.execute(
            select(ApiToken).where(ApiToken.user_id == user.id).order_by(ApiToken.created_at.desc())
        ).scalars()
    )


def revoke_api_token(db: Session, user: User, token_id: str) -> bool:
    token = db.get(ApiToken, token_id)
    if token is None or token.user_id != user.id:
        return False
    db.delete(token)
    db.commit()
    return True


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
