"""Startup smoke test."""
import asyncio
import pathlib

async def check():
    from app.database import create_tables
    from app.rules import load_rule_packs
    from app.config import settings
    from app.ml.registry import registry as ml_registry

    await create_tables()
    load_rule_packs()

    artifacts_dir = (
        pathlib.Path(settings.ml_artifacts_dir)
        if settings.ml_artifacts_dir
        else None
    )
    ml_registry.startup(ml_enabled=settings.ml_enabled, artifacts_dir=artifacts_dir)

    print(f"ML_ENABLED setting: {settings.ml_enabled}")
    print(f"ML layer active:    {ml_registry.is_enabled()}")
    print(f"Models loaded:      {[c.model_id for c in ml_registry.model_cards()]}")

    # Check all routers import cleanly
    from app.routers.health import router as health_router
    from app.routers.disruptions import router as disruptions_router
    from app.routers.shipments import router as shipments_router
    from app.routers.cold_chain import router as cold_chain_router
    from app.routers.fleet import router as fleet_router
    from app.routers.priority_queue import router as pq_router
    from app.routers.assistant import router as assistant_router
    from app.routers.predictions import router as predictions_router
    print("All routers imported OK")

    # Check the ORM has PredictionRow
    from app.models.orm import PredictionRow
    print(f"PredictionRow table: {PredictionRow.__tablename__}")

    # Check domain Prediction model
    from app.models.domain import Prediction, PriorityItemKind
    print(f"PriorityItemKind members: {[k.value for k in PriorityItemKind]}")

    print("\n[OK] Backend startup smoke test passed.")

asyncio.run(check())
