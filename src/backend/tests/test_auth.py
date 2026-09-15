"""
tests/test_auth.py — Authentication test suite.

Tests:
  - signup + login round trip
  - wrong password rejected (same status as wrong email)
  - duplicate email rejected with 409
  - gated endpoint returns 401 without cookie, 200 with cookie
  - rate limiter trips at 6th attempt, returns 429 with Retry-After
  - logout clears session (subsequent /me returns 401)
  - demo user exists after seeding
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.main import app as fastapi_app
from app.database import Base, get_db
import app.auth.models  # noqa: F401 — ensure UserRow is on Base.metadata

# ── In-memory SQLite engine for tests ─────────────────────────────────────────
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, expire_on_commit=False)


async def override_get_db():
    async with TestSessionLocal() as session:
        yield session


@pytest.fixture(autouse=True)
async def setup_db():
    """Create all tables before each test, drop after."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    fastapi_app.dependency_overrides[get_db] = override_get_db
    yield
    fastapi_app.dependency_overrides.clear()
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app), base_url="http://test"
    ) as c:
        yield c


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _signup(client: AsyncClient, email="test@example.com", password="securepass99", name="Test User"):
    return await client.post("/api/v1/auth/signup", json={
        "email": email, "password": password, "full_name": name
    })


async def _login(client: AsyncClient, email="test@example.com", password="securepass99"):
    return await client.post("/api/v1/auth/login", json={
        "email": email, "password": password
    })


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_signup_returns_201_and_user(client: AsyncClient):
    r = await _signup(client)
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "test@example.com"
    assert body["fullName"] == "Test User"
    assert "passwordHash" not in body
    assert "password" not in body


@pytest.mark.asyncio
async def test_signup_sets_session_cookie(client: AsyncClient):
    r = await _signup(client)
    assert r.status_code == 201
    assert "cf_session" in r.cookies


@pytest.mark.asyncio
async def test_login_round_trip(client: AsyncClient):
    await _signup(client)
    r = await _login(client)
    assert r.status_code == 200
    assert "cf_session" in r.cookies
    # /me should return the user
    me = await client.get("/api/v1/auth/me", cookies=r.cookies)
    assert me.status_code == 200
    assert me.json()["email"] == "test@example.com"


@pytest.mark.asyncio
async def test_wrong_password_rejected(client: AsyncClient):
    await _signup(client)
    r = await _login(client, password="wrongpassword")
    assert r.status_code == 401
    # Same body shape as wrong email
    assert "passwordHash" not in r.json()


@pytest.mark.asyncio
async def test_wrong_email_rejected(client: AsyncClient):
    r = await _login(client, email="nobody@example.com", password="anything12")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_wrong_email_and_wrong_password_same_status(client: AsyncClient):
    """User enumeration: both wrong email and wrong password must return 401."""
    await _signup(client)
    r_bad_email = await _login(client, email="nobody@example.com", password="securepass99")
    r_bad_pass = await _login(client, email="test@example.com", password="wrongpassword")
    assert r_bad_email.status_code == r_bad_pass.status_code == 401
    assert r_bad_email.json()["detail"] == r_bad_pass.json()["detail"]


@pytest.mark.asyncio
async def test_duplicate_email_rejected(client: AsyncClient):
    await _signup(client)
    r = await _signup(client)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_gated_endpoint_returns_401_without_cookie(client: AsyncClient):
    r = await client.get("/api/v1/disruptions")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_gated_endpoint_returns_200_with_cookie(client: AsyncClient):
    await _signup(client)
    login_r = await _login(client)
    assert "cf_session" in login_r.cookies
    r = await client.get("/api/v1/disruptions", cookies=login_r.cookies)
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_rate_limiter_trips_at_sixth_attempt(client: AsyncClient):
    """5 bad attempts allowed; 6th must return 429 with Retry-After."""
    # Reset the in-memory store before this test
    from app.auth.service import _rate_store
    _rate_store.clear()

    await _signup(client, email="rate@example.com")
    for i in range(5):
        r = await client.post("/api/v1/auth/login", json={
            "email": "rate@example.com", "password": "wrongpassword"
        })
        assert r.status_code == 401, f"attempt {i+1} should be 401, got {r.status_code}"

    r = await client.post("/api/v1/auth/login", json={
        "email": "rate@example.com", "password": "wrongpassword"
    })
    assert r.status_code == 429
    assert "Retry-After" in r.headers
    assert int(r.headers["Retry-After"]) > 0


@pytest.mark.asyncio
async def test_logout_clears_session(client: AsyncClient):
    await _signup(client)
    login_r = await _login(client)
    cookies = login_r.cookies

    # Logout
    logout_r = await client.post("/api/v1/auth/logout", cookies=cookies)
    assert logout_r.status_code == 204

    # /me with old cookie should now fail (cookie is cleared)
    # The server clears the cookie via Set-Cookie with empty value/expiry.
    # httpx propagates the cleared cookie so the jar no longer sends it.
    me_r = await client.get("/api/v1/auth/me")
    assert me_r.status_code == 401


@pytest.mark.asyncio
async def test_me_without_cookie_returns_401(client: AsyncClient):
    r = await client.get("/api/v1/auth/me")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_weak_password_rejected(client: AsyncClient):
    r = await client.post("/api/v1/auth/signup", json={
        "email": "weak@example.com",
        "password": "password",
        "full_name": "Weak User",
    })
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_short_password_rejected(client: AsyncClient):
    r = await client.post("/api/v1/auth/signup", json={
        "email": "short@example.com",
        "password": "abc123",
        "full_name": "Short User",
    })
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_demo_user_exists_after_seed():
    """
    After _seed_demo_user runs, demo@coldfront.app can log in.
    We call the function directly against an in-memory DB.
    """
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Temporarily redirect DB
    fastapi_app.dependency_overrides[get_db] = override_get_db

    from app.auth.service import _rate_store
    _rate_store.clear()

    # Seed the demo user directly
    from app.seed import _seed_demo_user

    # Patch AsyncSessionLocal to use the test engine
    import app.seed as seed_module
    original = seed_module.AsyncSessionLocal
    seed_module.AsyncSessionLocal = TestSessionLocal
    try:
        await _seed_demo_user()
    finally:
        seed_module.AsyncSessionLocal = original

    # Now test login
    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app), base_url="http://test"
    ) as c:
        r = await c.post("/api/v1/auth/login", json={
            "email": "demo@coldfront.app",
            "password": "demo-control-tower",
        })
        assert r.status_code == 200
        assert r.json()["isDemo"] is True

    fastapi_app.dependency_overrides.clear()
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
