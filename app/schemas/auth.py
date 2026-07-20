"""Esquemas de autenticación y usuario."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(default="", max_length=255)


class UserLogin(BaseModel):
    username: str  # acepta username o email
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    email: EmailStr
    full_name: str
    role: str
    is_active: bool
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ApiTokenCreate(BaseModel):
    name: str = Field(default="default", max_length=128)


class ApiTokenOut(BaseModel):
    """Respuesta al crear un token. Solo muestra el valor plano una vez."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    token: str  # valor plano (solo en la creación)
    created_at: datetime
