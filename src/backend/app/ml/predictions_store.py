"""
app/ml/predictions_store.py — Async DB read/write for the predictions table.

Thin data-access layer. No business logic here — just the CRUD operations
the routers and the batch forecaster need.

All writes are upsert-by-id (idempotent) so the batch scheduler can rerun
without accumulating duplicates.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain import Prediction
from app.models.orm import PredictionRow


async def upsert_prediction(db: AsyncSession, prediction: Prediction) -> None:
    """
    Insert or replace a prediction row (upsert by primary key id).
    SQLite-specific; replace with proper upsert for PostgreSQL.
    """
    stmt = sqlite_insert(PredictionRow).values(
        id=prediction.id,
        model_id=prediction.model_id,
        model_version=prediction.model_version,
        subject_type=prediction.subject_type,
        subject_id=prediction.subject_id,
        predicted_at=prediction.predicted_at,
        horizon_hours=prediction.horizon_hours,
        value=prediction.value,
        confidence=prediction.confidence,
        features=prediction.features,
        baseline_value=prediction.baseline_value,
    )
    stmt = stmt.on_conflict_do_replace()
    await db.execute(stmt)
    await db.commit()


async def get_predictions_for_subject(
    db: AsyncSession,
    subject_type: str,
    subject_id: str,
    *,
    limit: int = 20,
) -> list[PredictionRow]:
    """Return the most recent predictions for a given subject (shipment / leg)."""
    stmt = (
        select(PredictionRow)
        .where(
            PredictionRow.subject_type == subject_type,
            PredictionRow.subject_id == subject_id,
        )
        .order_by(PredictionRow.predicted_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_excursion_risk_predictions(
    db: AsyncSession,
    *,
    limit: int = 50,
) -> list[PredictionRow]:
    """
    Return the latest excursion-risk predictions across all in-transit cold
    chain shipments, ranked by value (probability) descending.
    """
    stmt = (
        select(PredictionRow)
        .where(PredictionRow.model_id == "excursion_forecaster")
        .order_by(PredictionRow.value.desc(), PredictionRow.predicted_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def delete_stale_predictions(
    db: AsyncSession,
    *,
    older_than: datetime,
) -> int:
    """Purge predictions older than a cutoff (used by the batch scheduler)."""
    stmt = delete(PredictionRow).where(PredictionRow.predicted_at < older_than)
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount


def prediction_row_to_domain(row: PredictionRow) -> Prediction:
    """Convert an ORM row to the Prediction domain model."""
    return Prediction(
        id=row.id,
        model_id=row.model_id,
        model_version=row.model_version,
        subject_type=row.subject_type,
        subject_id=row.subject_id,
        predicted_at=row.predicted_at,
        horizon_hours=row.horizon_hours,
        value=row.value,
        confidence=row.confidence,
        features=row.features,
        baseline_value=row.baseline_value,
    )
