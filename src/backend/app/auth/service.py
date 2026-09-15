"""
app/auth/service.py — password hashing, JWT creation/decoding, rate limiting.

Password hashing: bcrypt (cost 12). Argon2id would be preferable for new
deployments — swap by installing argon2-cffi and replacing the hash/verify
functions below; the rest of the module is unchanged.

JWT: HS256, 60-minute lifetime, signed with SESSION_SECRET from config.
A warning is logged on every startup when the development default is in use.

Rate limiter: in-memory per-process. 5 attempts per email per 15 minutes.
NOTE: a load balancer without sticky routing, or a multi-process server,
would require a shared store (Redis). For a single-process hackathon demo
this is sufficient.
"""
from __future__ import annotations

import hmac
import logging
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from app.config import settings

logger = logging.getLogger(__name__)

# ── Session secret ────────────────────────────────────────────────────────────
_DEV_SECRET = "dev-secret-change-in-prod-2025x!"
_SECRET = settings.session_secret

if _SECRET == _DEV_SECRET:
    logger.warning(
        "SESSION_SECRET is using the development default. "
        "Set SESSION_SECRET to a strong random value before any non-local deployment."
    )

# ── JWT config ────────────────────────────────────────────────────────────────
_ALGORITHM = "HS256"
_TOKEN_LIFETIME_MINUTES = 60

# ── Rate limiter ──────────────────────────────────────────────────────────────
# Per-process in-memory store: email → deque of attempt timestamps (float seconds).
_RATE_LIMIT_ATTEMPTS = 5
_RATE_LIMIT_WINDOW_SECONDS = 15 * 60  # 15 minutes
_rate_store: dict[str, deque[float]] = {}


def _check_rate_limit(email: str) -> tuple[bool, int]:
    """
    Returns (allowed: bool, retry_after_seconds: int).
    Allowed is True if the attempt is permitted.
    """
    now = time.time()
    window_start = now - _RATE_LIMIT_WINDOW_SECONDS
    attempts = _rate_store.setdefault(email, deque())

    # Remove expired entries
    while attempts and attempts[0] < window_start:
        attempts.popleft()

    if len(attempts) >= _RATE_LIMIT_ATTEMPTS:
        oldest = attempts[0]
        retry_after = int(oldest + _RATE_LIMIT_WINDOW_SECONDS - now) + 1
        return False, retry_after

    attempts.append(now)
    return True, 0


def record_failed_attempt(email: str) -> tuple[bool, int]:
    """Record a failed login attempt. Returns (allowed, retry_after)."""
    return _check_rate_limit(email)


def clear_rate_limit(email: str) -> None:
    """Clear rate limit state on successful login."""
    _rate_store.pop(email, None)


# ── Password hashing ──────────────────────────────────────────────────────────
# Cost factor 12 — ~300ms on a typical laptop, acceptable for login.
_BCRYPT_ROUNDS = 12

# Dummy hash used for timing-safe failure when email does not exist.
# Pre-computed so the verify call takes the same time as a real lookup.
_DUMMY_HASH: bytes = bcrypt.hashpw(b"dummy-password-for-timing", bcrypt.gensalt(_BCRYPT_ROUNDS))


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of the plaintext password."""
    hashed = bcrypt.hashpw(plain.encode(), bcrypt.gensalt(_BCRYPT_ROUNDS))
    return hashed.decode()


def verify_password(plain: str, hashed: str | None) -> bool:
    """
    Timing-safe password check. If hashed is None (email not found), we still
    run bcrypt.checkpw against the dummy hash so the response time is identical
    to a real lookup — this prevents user enumeration via timing.
    """
    check_against = hashed.encode() if hashed else _DUMMY_HASH
    plain_bytes = plain.encode()
    result = bcrypt.checkpw(plain_bytes, check_against)
    # Never return True when hashed was None — the account does not exist
    return result and hashed is not None


# ── JWT tokens ────────────────────────────────────────────────────────────────

def create_token(user_id: str, email: str, is_demo: bool) -> str:
    """Create a signed JWT with 60-minute expiry."""
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": user_id,
        "email": email,
        "is_demo": is_demo,
        "iat": now,
        "exp": now + timedelta(minutes=_TOKEN_LIFETIME_MINUTES),
    }
    return jwt.encode(payload, _SECRET, algorithm=_ALGORITHM)


def decode_token(token: str) -> dict[str, Any] | None:
    """
    Decode and verify a JWT. Returns the payload dict, or None if invalid/expired.
    Never raises — callers check for None.
    """
    try:
        return jwt.decode(token, _SECRET, algorithms=[_ALGORITHM])
    except jwt.PyJWTError:
        return None


# ── Cookie helpers ────────────────────────────────────────────────────────────
COOKIE_NAME = "cf_session"


def cookie_kwargs(debug: bool) -> dict[str, Any]:
    """Return kwargs for Response.set_cookie."""
    return {
        "key": COOKIE_NAME,
        "httponly": True,
        "samesite": "lax",
        "secure": not debug,
        "max_age": _TOKEN_LIFETIME_MINUTES * 60,
        "path": "/",
    }
