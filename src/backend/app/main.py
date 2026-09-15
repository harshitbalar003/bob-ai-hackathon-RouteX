"""
app/main.py — FastAPI application factory.

Run with:
    uvicorn app.main:app --reload

Works from a clean clone with no .env file.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import create_tables
from app.rules import load_rule_packs
import app.auth.models  # noqa: F401 — registers UserRow on Base.metadata


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create tables (idempotent), warm rule pack cache, load ML registry
    await create_tables()
    load_rule_packs()

    # ML layer startup — non-fatal; disabled by default (ML_ENABLED=false)
    import pathlib
    from app.config import settings
    from app.ml.registry import registry as ml_registry

    artifacts_dir = (
        pathlib.Path(settings.ml_artifacts_dir)
        if settings.ml_artifacts_dir
        else None
    )
    ml_registry.startup(ml_enabled=settings.ml_enabled, artifacts_dir=artifacts_dir)

    # Run the batch excursion-risk forecaster once at startup if ML is enabled.
    # This populates the predictions table immediately so the first API response
    # is not empty. A production deployment would schedule this on a timer.
    if ml_registry.is_enabled():
        import asyncio
        from app.ml.batch_forecaster import run_batch_forecast
        from app.database import AsyncSessionLocal
        try:
            async with AsyncSessionLocal() as db:
                await run_batch_forecast(db)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "Batch forecast at startup failed (non-fatal): %s", exc
            )

    yield
    # Shutdown: nothing to clean up for SQLite


app = FastAPI(
    title="Supply Chain Control Tower API",
    description=(
        "Deterministic backend for supply chain disruption response and "
        "cold-chain compliance. Every verdict carries its Decision."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten for production; open for hackathon judges
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
from fastapi import Depends  # noqa: E402
from app.auth import current_user  # noqa: E402
from app.auth.router import router as auth_router  # noqa: E402
from app.routers.health import router as health_router  # noqa: E402
from app.routers.disruptions import router as disruptions_router  # noqa: E402
from app.routers.shipments import router as shipments_router  # noqa: E402
from app.routers.cold_chain import router as cold_chain_router  # noqa: E402
from app.routers.fleet import router as fleet_router  # noqa: E402
from app.routers.priority_queue import router as pq_router  # noqa: E402
from app.routers.stream import router as stream_router  # noqa: E402
from app.routers.assistant import router as assistant_router  # noqa: E402
from app.routers.predictions import router as predictions_router  # noqa: E402

# Auth and health are open; all other routers require a valid session cookie.
_auth_dep = [Depends(current_user)]

app.include_router(auth_router, prefix="/api/v1")
app.include_router(health_router, prefix="/api/v1")
app.include_router(disruptions_router, prefix="/api/v1", dependencies=_auth_dep)
app.include_router(shipments_router, prefix="/api/v1", dependencies=_auth_dep)
app.include_router(cold_chain_router, prefix="/api/v1", dependencies=_auth_dep)
app.include_router(fleet_router, prefix="/api/v1", dependencies=_auth_dep)
app.include_router(pq_router, prefix="/api/v1", dependencies=_auth_dep)
app.include_router(stream_router, prefix="/api/v1", dependencies=_auth_dep)
app.include_router(assistant_router, prefix="/api/v1", dependencies=_auth_dep)
app.include_router(predictions_router, prefix="/api/v1", dependencies=_auth_dep)
