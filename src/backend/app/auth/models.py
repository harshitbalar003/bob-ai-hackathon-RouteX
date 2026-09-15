"""
app/auth/models.py — ORM row and Pydantic schemas for users.

The password hash is never returned in any API response.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# ── Weak-password blocklist (no complexity theatre) ──────────────────────────
_WEAK_PASSWORDS = {
    "password",
    "12345678",
    "password1",
    "qwerty123",
    "coldfront",
    "demo1234",
    "letmein!",
    "welcome1",
    "abc12345",
    "iloveyou",
    "sunshine",
}


# ── ORM ───────────────────────────────────────────────────────────────────────

class UserRow(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    full_name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


# ── Pydantic schemas ───────────────────────────────────────────────────────────

class SignupIn(BaseModel):
    email: EmailStr
    password: str
    full_name: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if v.lower() in _WEAK_PASSWORDS:
            raise ValueError(
                "This password is too common — choose something less predictable"
            )
        return v

    @field_validator("full_name")
    @classmethod
    def full_name_nonempty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name is required")
        return v


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    full_name: str = Field(alias="full_name", serialization_alias="fullName")
    is_demo: bool = Field(alias="is_demo", serialization_alias="isDemo")

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
        "by_alias": True,
    }
