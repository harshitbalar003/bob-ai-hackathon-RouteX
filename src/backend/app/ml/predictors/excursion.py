"""
app/ml/predictors/excursion.py — Excursion breach-risk predictor.

Single responsibility: accept raw shipment context, call features.py to build
the feature vector, call registry.predict_excursion_risk(), wrap the result
in a Prediction domain object (or return None).

The caller (router or priority-queue scheduler) never touches sklearn directly.

Boundary guarantee:
  - This module does NOT import from app.engines.cold_chain
  - It does NOT set severity, citation, or disposition
  - It does NOT write to the excursions table
  - A None return is always a valid outcome; callers must handle it
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.ml.features import (
    FEATURE_NAMES,
    HORIZON_HOURS,
    MIN_READINGS_IN_WINDOW,
    baseline_predict,
    build_feature_vector,
)
from app.ml.registry import MODEL_EXCURSION_FORECASTER, registry
from app.models.domain import Prediction


def predict_breach_risk(
    *,
    window_readings: list[dict],
    shipment_id: str,
    leg_id: str,
    temp_range_min: float,
    temp_range_max: float,
    reefer_setpoint_c: float,
    leg_arrives_at: datetime,
    next_transfer_within_4h: bool,
    dwell_status: str,
    ambient_temp_forecast_c: float,
    container_type: str,
    prediction_timestamp: datetime | None = None,
) -> Prediction | None:
    """
    Predict P(temperature breach within 4 hours) for one in-transit cold-chain
    shipment at the current moment.

    Returns None when:
      - ML_ENABLED=false (registry returns None)
      - Fewer than MIN_READINGS_IN_WINDOW readings in window
      - Any inference error (logged inside registry; never re-raised here)

    Returns a Prediction with:
      - value: calibrated P(breach), 0–1
      - confidence: same as value for binary classifier
      - baseline_value: B1 heuristic output (0 or 1)
      - features: the full feature vector used
    """
    if prediction_timestamp is None:
        prediction_timestamp = datetime.now(timezone.utc)

    if len(window_readings) < MIN_READINGS_IN_WINDOW:
        return None

    try:
        fv = build_feature_vector(
            window_readings,
            temp_range_min=temp_range_min,
            temp_range_max=temp_range_max,
            reefer_setpoint_c=reefer_setpoint_c,
            leg_arrives_at=leg_arrives_at,
            next_transfer_within_4h=next_transfer_within_4h,
            dwell_status=dwell_status,
            ambient_temp_forecast_c=ambient_temp_forecast_c,
            container_type=container_type,
            prediction_timestamp=prediction_timestamp,
        )
    except Exception:
        return None

    proba = registry.predict_excursion_risk(fv)
    if proba is None:
        return None

    baseline = float(baseline_predict(fv))

    card = next(
        (c for c in registry.model_cards() if c.model_id == MODEL_EXCURSION_FORECASTER),
        None,
    )
    model_version = card.version if card else "unknown"

    return Prediction(
        id=f"pred-{shipment_id}-{leg_id}-{int(prediction_timestamp.timestamp())}",
        model_id=MODEL_EXCURSION_FORECASTER,
        model_version=model_version,
        subject_type="shipment",
        subject_id=shipment_id,
        predicted_at=prediction_timestamp,
        horizon_hours=HORIZON_HOURS,
        value=round(proba, 4),
        confidence=round(proba, 4),
        features={k: fv[k] for k in FEATURE_NAMES},
        baseline_value=baseline,
    )
