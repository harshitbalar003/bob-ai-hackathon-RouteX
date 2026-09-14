"""
app/routers/cold_chain.py

GET  /api/v1/cold-chain/excursions
POST /api/v1/cold-chain/ingest
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.domain import Excursion, SensorReading
from app.models.orm import ExcursionRow, SensorReadingRow, ShipmentRow

router = APIRouter(prefix="/cold-chain", tags=["cold-chain"])


@router.get("/excursions", response_model=list[Excursion])
async def list_excursions(
    db: Annotated[AsyncSession, Depends(get_db)],
    open_only: bool = Query(default=False),
    severity: Optional[str] = Query(default=None),
    shipment_id: Optional[str] = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[Excursion]:
    """
    Return open and recent excursions, ranked by severity then actionability.
    Severity order: critical > major > minor > informational.
    Actionability: detectedBeforeDelivery=True ranks above post-mortem.
    """
    stmt = select(ExcursionRow)
    if open_only:
        stmt = stmt.where(ExcursionRow.ended_at == None)
    if severity:
        stmt = stmt.where(ExcursionRow.severity == severity)
    if shipment_id:
        stmt = stmt.where(ExcursionRow.shipment_id == shipment_id)

    # Order by severity (custom) then actionability
    # SQLite: sort by string, so we use a CASE expression via raw order
    # For simplicity: fetch all and sort in Python (dataset is small)
    result = await db.execute(stmt)
    rows = result.scalars().all()

    _sev_rank = {"critical": 0, "major": 1, "minor": 2, "informational": 3}

    def _rank(row: ExcursionRow):
        sev = _sev_rank.get(row.severity, 99)
        actionable = 0 if row.detected_before_delivery else 1
        return (sev, actionable, row.started_at)

    rows_sorted = sorted(rows, key=_rank)
    rows_page = rows_sorted[skip : skip + limit]

    return [
        Excursion(
            id=r.id,
            shipmentId=r.shipment_id,
            legId=r.leg_id,
            startedAt=r.started_at.isoformat(),
            endedAt=r.ended_at.isoformat() if r.ended_at else None,
            peakTempC=r.peak_temp_c,
            minutesOutOfRange=r.minutes_out_of_range,
            degreeMinutes=r.degree_minutes,
            meanKineticTempC=r.mean_kinetic_temp_c,
            severity=r.severity,
            regulatoryBasis=r.citation,
            disposition=r.disposition,
            evidenceReadingIds=r.evidence_reading_ids,
            detectedBeforeDelivery=r.detected_before_delivery,
        )
        for r in rows_page
    ]


@router.post("/ingest")
async def ingest_readings(
    readings: list[SensorReading],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """
    Accept a batch of sensor readings. Deduplicates by canonical reading ID.
    Returns count of new readings inserted.
    """
    inserted = 0
    skipped = 0
    for r in readings:
        rid = r.reading_id
        existing = await db.get(SensorReadingRow, rid)
        if existing is not None:
            skipped += 1
            continue
        row = SensorReadingRow(
            id=rid,
            shipment_id=r.shipment_id,
            sensor_id=r.sensor_id,
            leg_id=r.leg_id,
            timestamp=r.timestamp,
            temp_c=r.temp_c,
            humidity_pct=r.humidity_pct,
            door_open=r.door_open,
        )
        db.add(row)
        inserted += 1

    await db.commit()
    return {
        "inserted": inserted,
        "skipped_duplicates": skipped,
        "total_received": len(readings),
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    }
