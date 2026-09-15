"""
app/auth/router.py — Four authentication endpoints.

POST /api/v1/auth/signup   — create account, return session cookie
POST /api/v1/auth/login    — verify credentials, return session cookie
POST /api/v1/auth/logout   — clear session cookie
GET  /api/v1/auth/me       — return current user (requires cookie)

Security properties:
- Wrong email and wrong password return the same HTTP status, body, and
  response time (timing-safe). Do not change the failure path to leak which
  accounts exist.
- Rate limiting: 5 failed attempts per email per 15 minutes → 429.
- Passwords are never logged, stored in plaintext, or returned in responses.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user
from app.auth.models import LoginIn, SignupIn, UserOut, UserRow
from app.auth.service import (
    COOKIE_NAME,
    clear_rate_limit,
    cookie_kwargs,
    create_token,
    hash_password,
    record_failed_attempt,
    verify_password,
)
from app.database import get_db

router = APIRouter(prefix="/auth", tags=["auth"])

# Debug mode: True when running with uvicorn --reload (typical dev usage).
# Used only to decide whether to set Secure on the cookie.
# A real deployment would read this from config; for the demo the default is fine.
_DEBUG = True  # cookies without Secure work on localhost HTTP


@router.post("/signup", status_code=status.HTTP_201_CREATED, response_model=UserOut)
async def signup(
    body: SignupIn,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    """Create a new user account and set the session cookie."""
    # Normalise email
    email = body.email.lower().strip()

    # Check for duplicate email
    existing = await db.execute(select(UserRow).where(UserRow.id == email).limit(1))
    # (query by email column, not id — just checking existence)
    dup_check = await db.execute(select(UserRow).where(UserRow.email == email).limit(1))
    if dup_check.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    user = UserRow(
        email=email,
        password_hash=hash_password(body.password),
        full_name=body.full_name.strip(),
        created_at=datetime.now(timezone.utc),
        is_demo=False,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = create_token(user.id, user.email, user.is_demo)
    kwargs = cookie_kwargs(_DEBUG)
    response.set_cookie(value=token, **kwargs)

    return UserOut.model_validate(user)


@router.post("/login", status_code=status.HTTP_200_OK, response_model=UserOut)
async def login(
    body: LoginIn,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    """
    Verify credentials and issue a session cookie.

    Timing safety: both "wrong email" and "wrong password" take the same time
    and return the same response. Do not expose which one failed.
    """
    email = body.email.lower().strip()

    # Rate limit check (before touching the DB so we can't be used for enumeration)
    allowed, retry_after = record_failed_attempt(email)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many login attempts — try again in {retry_after} seconds",
            headers={"Retry-After": str(retry_after)},
        )

    result = await db.execute(select(UserRow).where(UserRow.email == email).limit(1))
    user: UserRow | None = result.scalar_one_or_none()

    # verify_password handles the None case with a dummy hash so timing is identical
    if not verify_password(body.password, user.password_hash if user else None):
        # Do NOT differentiate between wrong email and wrong password
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    # Success — clear rate limit, update last_login_at
    clear_rate_limit(email)
    user.last_login_at = datetime.now(timezone.utc)  # type: ignore[union-attr]
    await db.commit()

    token = create_token(user.id, user.email, user.is_demo)  # type: ignore[union-attr]
    kwargs = cookie_kwargs(_DEBUG)
    response.set_cookie(value=token, **kwargs)

    return UserOut.model_validate(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    """Clear the session cookie."""
    response.delete_cookie(
        key=COOKIE_NAME,
        path="/",
        samesite="lax",
    )


@router.get("/me", response_model=UserOut)
async def me(user: UserRow = Depends(current_user)) -> UserOut:
    """Return the currently authenticated user. 401 if no valid session."""
    return UserOut.model_validate(user)
