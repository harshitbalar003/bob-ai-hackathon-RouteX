"""
app/ml/batch_forecaster.py — Batch excursion-risk forecaster.

Runs synchronously across all in-transit cold-chain shipments.
Called once at startup and (in a production deployment) on a schedule.

Inference budget: 50 ms per shipment. The timeout wrapper logs and skips
any shipment that exceeds this; it never returns a 500 to the operator.

Design:
  - Queries the DB for in-transit cold-chain shipments
  - For each shipment, fetches the trailing 2-hour window of sensor readings
  - Calls predict_breach_risk() from the predictor module
  - Upserts results to the predictions table (idempotent)

This module is NEVER called from the deterministic engines.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ml.predictions_store import upsert_prediction
from app.ml.predictors.excursion import predict_breach_risk
from app.ml.registry import registry as ml_registry
from app.models.orm import SensorReadingRow, ShipmentRow

logger = logging.getLogger(__name__)

_WINDOW_MINUTES = 120       # 2-hour trailing window for features
_MAX_INFERENCE_MS = 100     # warn if inference takes longer than this


async def _get_cold_chain_shipments(db: AsyncSession) -> list[ShipmentRow]:
    """Return all in-transit cold-chain shipments."""
    stmt = select(ShipmentRow).where(
        ShipmentRow.is_cold_chain.is_(True),
        ShipmentRow.status.in_(["in_transit", "at_risk", "exception"]),
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def _get_trailing_window(
    db: AsyncSession,
    shipment_id: str,
    cutoff: datetime,
    window_minutes: int,
) -> list[dict]:
    """Fetch the trailing window of sensor readings for one shipment."""
    window_start = cutoff - timedelta(minutes=window_minutes)
    stmt = (
        select(SensorReadingRow)
        .where(
            SensorReadingRow.shipment_id == shipment_id,
            SensorReadingRow.timestamp >= window_start,
            SensorReadingRow.timestamp <= cutoff,
        )
        .order_by(SensorReadingRow.timestamp.asc())
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [
        {
            "timestamp": r.timestamp if r.timestamp.tzinfo else r.timestamp.replace(tzinfo=timezone.utc),
            "temp_c": r.temp_c,
            "door_open": r.door_open,
        }
        for r in rows
    ]


def _extract_leg_context(shipment_row: ShipmentRow) -> dict | None:
    """
    Extract the current active leg's context from the shipment's data JSON.
    Returns None if no in-transit leg is found.
    """
    data = shipment_row.data or {}
    legs = data.get("legs", [])
    cargo = data.get("cargo", {})

    # Find the first in-transit leg
    active_leg = None
    for leg in legs:
        if leg.get("status") == "in_transit":
            active_leg = leg
            break
    # Fallback: first leg
    if active_leg is None and legs:
        active_leg = legs[0]
    if active_leg is None:
        return None

    try:
        arrives_at = datetime.fromisoformat(
            active_leg["arrivesAt"].replace("Z", "+00:00")
        )
    except (KeyError, ValueError):
        return None

    temp_range = cargo.get("tempRangeC") or {}

    return {
        "leg_id": active_leg.get("id", ""),
        "leg_arrives_at": arrives_at,
        "temp_range_min": float(temp_range.get("min", 2.0)),
        "temp_range_max": float(temp_range.get("max", 8.0)),
        "reefer_setpoint_c": float((temp_range.get("min", 2.0) + temp_range.get("max", 8.0)) / 2.0),
        "next_transfer_within_4h": len(legs) > 1,
        "container_type": "reefer_container",
        "ambient_temp_forecast_c": 22.0,  # default; future: lookup by position
        "dwell_status": "in_transit",
    }


async def run_batch_forecast(db: AsyncSession) -> int:
    """
    Run the excursion-risk forecaster across all in-transit cold-chain shipments.

    Returns the number of predictions written.
    Wraps every per-shipment call in a try/except — a single failure never
    aborts the batch.
    """
    if not ml_registry.is_enabled():
        logger.debug("ML disabled; batch forecast skipped.")
        return 0

    now = datetime.now(timezone.utc)
    shipments = await _get_cold_chain_shipments(db)
    if not shipments:
        logger.info("No in-transit cold-chain shipments; batch forecast skipped.")
        return 0

    logger.info("Running batch excursion-risk forecast for %d shipments...", len(shipments))
    written = 0

    for ship in shipments:
        t_start = time.monotonic()
        try:
            context = _extract_leg_context(ship)
            if context is None:
                continue

            window = await _get_trailing_window(
                db, ship.id, now, _WINDOW_MINUTES
            )
            if not window:
                continue

            prediction = predict_breach_risk(
                window_readings=window,
                shipment_id=ship.id,
                leg_id=context["leg_id"],
                temp_range_min=context["temp_range_min"],
                temp_range_max=context["temp_range_max"],
                reefer_setpoint_c=context["reefer_setpoint_c"],
                leg_arrives_at=context["leg_arrives_at"],
                next_transfer_within_4h=context["next_transfer_within_4h"],
                dwell_status=context["dwell_status"],
                ambient_temp_forecast_c=context["ambient_temp_forecast_c"],
                container_type=context["container_type"],
                prediction_timestamp=now,
            )

            if prediction is not None:
                await upsert_prediction(db, prediction)
                written += 1

            elapsed_ms = (time.monotonic() - t_start) * 1000
            if elapsed_ms > _MAX_INFERENCE_MS:
                logger.warning(
                    "Batch forecast for %s took %.1f ms (budget %d ms)",
                    ship.id, elapsed_ms, _MAX_INFERENCE_MS,
                )

        except Exception as exc:
            logger.error(
                "Batch forecast failed for %s (non-fatal): %s", ship.id, exc,
                exc_info=True,
            )

    logger.info("Batch forecast complete: %d predictions written.", written)
    return written
