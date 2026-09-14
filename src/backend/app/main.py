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


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create tables (idempotent) and warm rule pack cache
    await create_tables()
    load_rule_packs()
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
from app.routers.health import router as health_router  # noqa: E402
from app.routers.disruptions import router as disruptions_router  # noqa: E402
from app.routers.shipments import router as shipments_router  # noqa: E402
from app.routers.cold_chain import router as cold_chain_router  # noqa: E402
from app.routers.fleet import router as fleet_router  # noqa: E402
from app.routers.priority_queue import router as pq_router  # noqa: E402
from app.routers.stream import router as stream_router  # noqa: E402
from app.routers.assistant import router as assistant_router  # noqa: E402

app.include_router(health_router, prefix="/api/v1")
app.include_router(disruptions_router, prefix="/api/v1")
app.include_router(shipments_router, prefix="/api/v1")
app.include_router(cold_chain_router, prefix="/api/v1")
app.include_router(fleet_router, prefix="/api/v1")
app.include_router(pq_router, prefix="/api/v1")
app.include_router(stream_router, prefix="/api/v1")
app.include_router(assistant_router, prefix="/api/v1")
