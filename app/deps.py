"""Dependencias reutilizables en FastAPI."""
from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models.api_token import ApiToken
from app.models.user import Role, User
from app.auth.security import decode_token


# OAuth2 para Swagger UI (formulario username/password)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def get_db() -> Session:  # type: ignore[override]
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------- Sesión por cookie (UI Jinja2) ----------

def get_current_user_optional(
    request: Request,
    db: Session = Depends(get_db),
) -> Optional[User]:
    """Lee el JWT desde cookie 'access_token'. Devuelve None si no hay sesión."""
    token = request.cookies.get("access_token")
    if not token:
        return None
    # Acepta formato "Bearer xxx" o solo el token.
    if token.lower().startswith("bearer "):
        token = token[7:]
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        return None
    return user


def require_user(user: Optional[User] = Depends(get_current_user_optional)) -> User:
    """Dependencia para rutas de UI que requieren sesión."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/auth/login"},
        )
    return user


def require_admin(user: User = Depends(require_user)) -> User:
    if user.role != Role.ADMIN:
        raise HTTPException(status_code=403, detail="Se requiere rol admin.")
    return user


# ---------- API por Bearer token (JWT o API key) ----------

def get_current_user_api(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Autenticación para endpoints REST: soporta JWT o API key (pe_...)."""
    # 1) Intentar API key primero si viene en header Authorization: Bearer pe_xxx
    auth_header = request.headers.get("authorization", "")
    bearer = auth_header.replace("Bearer ", "").replace("bearer ", "").strip() if auth_header else ""
    if bearer.startswith("pe_"):
        user = _user_from_api_token(bearer, db)
        if user:
            return user
        raise HTTPException(401, "API token inválido.")

    # 2) JWT
    if not token:
        raise HTTPException(401, "No autenticado.")
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(401, "Token inválido o expirado.")
    user = db.get(User, payload.get("sub"))
    if user is None or not user.is_active:
        raise HTTPException(401, "Usuario inválido.")
    return user


def _user_from_api_token(raw_token: str, db: Session) -> Optional[User]:
    import hashlib

    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    api_token = db.query(ApiToken).filter(ApiToken.token_hash == token_hash).first()
    if api_token is None or not api_token.is_active:
        return None
    if api_token.expires_at is not None:
        from datetime import datetime, timezone

        if datetime.now(timezone.utc) > api_token.expires_at:
            return None
    user = db.get(User, api_token.user_id)
    if user is None or not user.is_active:
        return None
    # Actualizar último uso
    from datetime import datetime, timezone

    api_token.last_used_at = datetime.now(timezone.utc)
    db.commit()
    return user


# Evasion de "settings importado pero no usado" si cambia en el futuro.
_ = settings
