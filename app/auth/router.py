"""Router API de autenticación (JSON).

Endpoints REST:
  POST /api/v1/auth/register
  POST /api/v1/auth/login       -> { access_token, user }
  GET  /api/v1/auth/me
  POST /api/v1/auth/tokens      -> crea API key
  GET  /api/v1/auth/tokens
  DELETE /api/v1/auth/tokens/{id}
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.auth.service import (
    AuthError,
    create_api_token,
    list_api_tokens,
    login_user,
    register_user,
    revoke_api_token,
)
from app.deps import get_current_user_api, get_db
from app.models.user import User
from app.schemas.auth import (
    ApiTokenCreate,
    ApiTokenOut,
    TokenResponse,
    UserCreate,
    UserOut,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=201)
def api_register(data: UserCreate, db: Session = Depends(get_db)):
    try:
        return register_user(db, data)
    except AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/login", response_model=TokenResponse)
def api_login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    try:
        user, token = login_user(db, form.username, form.password)
    except AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserOut.model_validate(user, from_attributes=True),
    )


@router.get("/me", response_model=UserOut)
def api_me(user: User = Depends(get_current_user_api)):
    return user


@router.post("/tokens", response_model=ApiTokenOut, status_code=201)
def api_create_token(
    data: ApiTokenCreate,
    user: User = Depends(get_current_user_api),
    db: Session = Depends(get_db),
):
    token, raw = create_api_token(db, user, data.name)
    return ApiTokenOut(id=token.id, name=token.name, token=raw, created_at=token.created_at)


@router.get("/tokens")
def api_list_tokens(
    user: User = Depends(get_current_user_api),
    db: Session = Depends(get_db),
):
    tokens = list_api_tokens(db, user)
    return [
        {
            "id": t.id,
            "name": t.name,
            "created_at": t.created_at.isoformat(),
            "last_used_at": t.last_used_at.isoformat() if t.last_used_at else None,
            "is_active": t.is_active,
        }
        for t in tokens
    ]


@router.delete("/tokens/{token_id}", status_code=204)
def api_revoke_token(
    token_id: str,
    user: User = Depends(get_current_user_api),
    db: Session = Depends(get_db),
):
    if not revoke_api_token(db, user, token_id):
        raise HTTPException(404, "Token no encontrado.")
    return None
