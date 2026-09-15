"""
app/auth/dependencies.py — FastAPI dependency that extracts and validates
the session cookie on protected routes.

Usage:
    from app.auth import current_user
    ...
    async def my_endpoint(user: UserRow = Depends(current_user)):
        ...
"""
from __future__ import annotations

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import UserRow
from app.auth.service import COOKIE_NAME, decode_token
from app.database import get_db


async def current_user(
    db: AsyncSession = Depends(get_db),
    cf_session: str | None = Cookie(default=None, alias=COOKIE_NAME),
) -> UserRow:
    """
    Extracts the JWT from the httpOnly session cookie, validates it, and
    returns the UserRow. Raises 401 if the cookie is absent, expired, or invalid.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if cf_session is None:
        raise credentials_exception

    payload = decode_token(cf_session)
    if payload is None:
        raise credentials_exception

    user_id: str | None = payload.get("sub")
    if user_id is None:
        raise credentials_exception

    result = await db.execute(select(UserRow).where(UserRow.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception

    return user
