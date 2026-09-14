"""
app/routers/disruptions.py

GET /api/v1/disruptions
GET /api/v1/disruptions/{id}
GET /api/v1/disruptions/{id}/impact
"""
from __future__ import annotations

import json
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.engines.impact import assess_disruption_impact
from app.models.domain import (
    CircleArea,
    Disruption,
    DisruptionType,
    GeoPoint,
    ImpactScore,
    PolygonArea,
    Severity,
    Shipment,
)
from app.models.orm import DisruptionRow, ShipmentRow

router = APIRouter(prefix="/disruptions", tags=["disruptions"])


def _row_to_disruption(row: DisruptionRow) -> Disruption:
    data = row.data
    area_raw = data["affectedArea"]
    if "center" in area_raw:
        c = area_raw["center"]
        area = CircleArea(
            center=GeoPoint(**c),
            radiusKm=area_raw["radiusKm"],
        )
    else:
        area = PolygonArea(polygon=area_raw["polygon"])
    return Disruption(
        id=data["id"],
        type=data["type"],
        headline=data["headline"],
        detail=data["detail"],
        severity=data["severity"],
        startedAt=data["startedAt"],
        expectedResolutionAt=data.get("expectedResolutionAt"),
        confidence=data["confidence"],
        source=data["source"],
        affectedArea=area,
        affectedNodes=data.get("affectedNodes", []),
    )


@router.get("", response_model=list[Disruption])
async def list_disruptions(
    db: Annotated[AsyncSession, Depends(get_db)],
    severity: Optional[str] = Query(default=None),
    type: Optional[str] = Query(default=None),
    active_only: bool = Query(default=True),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[Disruption]:
    stmt = select(DisruptionRow)
    if active_only:
        stmt = stmt.where(DisruptionRow.active == True)
    if severity:
        stmt = stmt.where(DisruptionRow.severity == severity)
    if type:
        stmt = stmt.where(DisruptionRow.type == type)
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [_row_to_disruption(r) for r in rows]


@router.get("/{disruption_id}", response_model=Disruption)
async def get_disruption(
    disruption_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Disruption:
    row = await db.get(DisruptionRow, disruption_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Disruption {disruption_id} not found")
    return _row_to_disruption(row)


@router.get("/{disruption_id}/impact", response_model=list[ImpactScore])
async def get_disruption_impact(
    disruption_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ImpactScore]:
    """
    Compute and return which shipments are impacted by this disruption,
    ranked by impact score descending. Each result carries a Decision.
    """
    dis_row = await db.get(DisruptionRow, disruption_id)
    if dis_row is None:
        raise HTTPException(status_code=404, detail=f"Disruption {disruption_id} not found")

    disruption = _row_to_disruption(dis_row)

    # Load all active shipments
    stmt = select(ShipmentRow).limit(500)
    result = await db.execute(stmt)
    shp_rows = result.scalars().all()

    from app.routers.shipments import _row_to_shipment
    shipments = [_row_to_shipment(r) for r in shp_rows]

    scores = assess_disruption_impact(disruption, shipments)
    return scores[skip : skip + limit]
