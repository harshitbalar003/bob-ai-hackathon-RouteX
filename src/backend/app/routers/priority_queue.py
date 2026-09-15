"""
app/routers/priority_queue.py

GET /api/v1/priority-queue
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.engines.priority_queue import build_priority_queue
from app.ml.predictions_store import get_excursion_risk_predictions
from app.ml.registry import registry as ml_registry
from app.models.orm import (
    ExcursionRow,
    FleetAssetRow,
    RedeploymentMatchRow,
    ShipmentRow,
)

router = APIRouter(prefix="/priority-queue", tags=["priority-queue"])


@router.get("")
async def get_priority_queue(
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    """
    The merged, ranked operator worklist.

    Merges open excursions, shipment exceptions/delays, idle assets, and
    (when ML_ENABLED=true) ML excursion-risk predictions into one comparable
    ordering. Predicted-risk items are visually distinct from confirmed
    excursions and always rank below them.
    """
    # Open + recent excursions
    exc_stmt = select(ExcursionRow).order_by(ExcursionRow.started_at.desc()).limit(20)
    exc_result = await db.execute(exc_stmt)
    excursion_rows = exc_result.scalars().all()

    # Impacted / delayed / exception shipments
    shp_stmt = select(ShipmentRow).where(
        ShipmentRow.status.in_(["exception", "delayed", "at_risk"])
    ).limit(100)
    shp_result = await db.execute(shp_stmt)
    shipment_rows = shp_result.scalars().all()

    # Idle assets
    fleet_stmt = select(FleetAssetRow).where(FleetAssetRow.status == "idle").limit(50)
    fleet_result = await db.execute(fleet_stmt)
    fleet_rows = fleet_result.scalars().all()

    # Assets with redeployment matches
    match_stmt = select(RedeploymentMatchRow.asset_id)
    match_result = await db.execute(match_stmt)
    asset_ids_with_match = set(match_result.scalars().all())

    # ML predictions (optional — empty list when disabled)
    prediction_rows = None
    if ml_registry.is_enabled():
        prediction_rows = await get_excursion_risk_predictions(db, limit=20)

    all_items = build_priority_queue(
        excursion_rows,
        shipment_rows,
        fleet_rows,
        asset_ids_with_match,
        prediction_rows=prediction_rows,
    )

    page = all_items[skip : skip + limit]

    return {
        "total": len(all_items),
        "skip": skip,
        "limit": limit,
        "items": [
            {
                **i.item.model_dump(by_alias=True),
                "score": i.score,
                "score_components": i.score_components,
            }
            for i in page
        ],
        "weights": {
            "severity": settings_weights(),
        },
    }


def settings_weights() -> dict:
    from app.config import settings
    return {
        "pq_weight_severity": settings.pq_weight_severity,
        "pq_weight_actionability": settings.pq_weight_actionability,
        "pq_weight_value": settings.pq_weight_value,
        "pq_weight_eta_slip": settings.pq_weight_eta_slip,
        "pq_weight_waste": settings.pq_weight_waste,
        "pq_weight_match": settings.pq_weight_match,
    }
