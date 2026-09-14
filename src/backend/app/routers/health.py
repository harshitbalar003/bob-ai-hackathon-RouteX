"""
app/routers/health.py — Health check endpoint.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from app.config import settings
from app.rules import load_rule_packs

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    packs = load_rule_packs()
    return {
        "status": "ok",
        "engine_version": settings.engine_version,
        "rule_packs_loaded": list(packs.keys()),
        "feature_sse": settings.feature_sse,
        "watsonx_enabled": settings.watsonx_enabled,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
