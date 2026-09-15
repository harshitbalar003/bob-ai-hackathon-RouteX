"""
app/routers/predictions.py — ML prediction endpoints.

Three endpoints:
  GET /api/v1/predictions/excursion-risk
      Ranked list of in-transit cold-chain shipments with breach-risk predictions.
      Only returns predictions when ML_ENABLED=true and model is loaded.
      Returns an empty list (not an error) when ML layer is disabled.

  GET /api/v1/shipments/{id}/predictions
      All live predictions for one shipment. Empty list when ML disabled.

  GET /api/v1/ml/models
      Model cards, versions, metrics, enabled state.
      Always returns (even when ML disabled) — shows the disabled state.

Visual contract (enforced in the frontend):
  - Predictions are NEVER shown as confirmed excursions
  - They carry a dashed/hatched badge, probability + horizon text
  - No regulatory citation is ever attached to a prediction
  - Below 50% confidence, shown as watch item not alert
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.ml.predictions_store import get_excursion_risk_predictions, get_predictions_for_subject, prediction_row_to_domain
from app.ml.registry import registry as ml_registry
from app.models.orm import ShipmentRow

router = APIRouter(tags=["predictions"])


@router.get("/predictions/excursion-risk")
async def list_excursion_risk_predictions(
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    """
    Return ranked excursion-risk predictions for in-transit cold-chain shipments.

    Empty list when ML_ENABLED=false — callers must handle this gracefully.
    Predictions are sorted by value (P(breach)) descending.

    UI contract:
      - Display as dashed badge: "68% risk within 4h"
      - No regulatory citation
      - Below 50% show as watch item, not alert
    """
    rows = await get_excursion_risk_predictions(db, limit=limit)
    predictions = [prediction_row_to_domain(r) for r in rows]

    return {
        "ml_enabled": ml_registry.is_enabled(),
        "count": len(predictions),
        "predictions": [p.model_dump() for p in predictions],
        "ui_contract": {
            "visual_treatment": "dashed",
            "show_regulatory_citation": False,
            "watch_threshold": 0.5,
            "horizon_hours": 4.0,
        },
    }


@router.get("/shipments/{shipment_id}/predictions")
async def get_shipment_predictions(
    shipment_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=20, ge=1, le=100),
) -> dict:
    """
    All live ML predictions for a single shipment.

    Returns an empty list when ML_ENABLED=false.
    The UI uses these to render the forecast band on the temperature chart —
    a forward-projected dashed line beyond the last real reading.
    """
    rows = await get_predictions_for_subject(
        db, subject_type="shipment", subject_id=shipment_id, limit=limit
    )
    predictions = [prediction_row_to_domain(r) for r in rows]

    return {
        "shipment_id": shipment_id,
        "ml_enabled": ml_registry.is_enabled(),
        "count": len(predictions),
        "predictions": [p.model_dump() for p in predictions],
    }


@router.get("/ml/models")
async def list_ml_models() -> dict:
    """
    List all loaded ML models with their cards, versions, metrics, and enabled state.

    Always returns (even when ML is disabled) so the frontend can display the
    disabled state and the docs/ml-models.md limitations.
    """
    cards = ml_registry.model_cards()
    return {
        "ml_enabled": ml_registry.is_enabled(),
        "model_count": len(cards),
        "models": [
            {
                "model_id": c.model_id,
                "version": c.version,
                "training_date": c.training_date,
                "feature_count": len(c.feature_names),
                "metrics": c.metrics,
                "known_limitations": c.known_limitations,
                "intended_use": c.intended_use,
                "not_for_production_decisions": c.not_for_production_decisions,
                "top_features": list(c.permutation_importance.items())[:5],
                "enabled": ml_registry.model_enabled(c.model_id),
            }
            for c in cards
        ],
        "disabled_message": (
            None if ml_registry.is_enabled()
            else (
                "ML layer is disabled (ML_ENABLED=false). "
                "The application is fully functional using heuristic baselines. "
                "Set ML_ENABLED=true after training artifacts are present."
            )
        ),
    }
