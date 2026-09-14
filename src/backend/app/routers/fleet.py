"""
app/routers/fleet.py

GET /api/v1/fleet/idle
GET /api/v1/fleet/redeployments
"""
from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.engines.fleet import compute_capacity_hours, rank_idle_assets
from app.models.domain import FleetAsset, RedeploymentMatch
from app.models.orm import FleetAssetRow, RedeploymentMatchRow

router = APIRouter(prefix="/fleet", tags=["fleet"])


def _row_to_asset(row: FleetAssetRow) -> FleetAsset:
    data = row.data
    return FleetAsset(
        id=data["id"],
        type=data["type"],
        status=data["status"],
        location=data["location"],
        idleSinceAt=data["idleSinceAt"],
        idleSinceHours=data["idleSinceHours"],
        capacity=data["capacity"],
        utilisationPct30d=data["utilisationPct30d"],
        reeferCapable=data["reeferCapable"],
        homeDepot=data["homeDepot"],
    )


@router.get("/idle", response_model=list[dict])
async def list_idle_assets(
    db: Annotated[AsyncSession, Depends(get_db)],
    reefer_only: bool = Query(default=False),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict]:
    """
    Return idle assets ranked by wasted capacity-hours (capacity × idle_hours).
    Includes capacity_hours field alongside each asset for transparency.
    """
    stmt = select(FleetAssetRow).where(FleetAssetRow.status == "idle")
    if reefer_only:
        stmt = stmt.where(FleetAssetRow.reefer_capable == True)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    assets = [_row_to_asset(r) for r in rows]
    ranked = rank_idle_assets(assets)
    page = ranked[skip : skip + limit]
    return [
        {
            **a.model_dump(by_alias=True),
            "capacity_hours": round(compute_capacity_hours(a), 1),
        }
        for a in page
    ]


@router.get("/redeployments", response_model=list[RedeploymentMatch])
async def list_redeployment_matches(
    db: Annotated[AsyncSession, Depends(get_db)],
    asset_id: Optional[str] = Query(default=None),
    shipment_id: Optional[str] = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[RedeploymentMatch]:
    """
    Return pre-computed redeployment matches from the DB (seeded from fixture).
    Sorted by hours_to_position ascending.
    """
    stmt = select(RedeploymentMatchRow).order_by(RedeploymentMatchRow.hours_to_position)
    if asset_id:
        stmt = stmt.where(RedeploymentMatchRow.asset_id == asset_id)
    if shipment_id:
        stmt = stmt.where(RedeploymentMatchRow.shipment_id == shipment_id)
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [
        RedeploymentMatch(
            assetId=r.asset_id,
            shipmentId=r.shipment_id,
            distanceKm=r.distance_km,
            hoursToPosition=r.hours_to_position,
            utilisationGainPct=r.utilisation_gain_pct,
            rationale=r.rationale,
            generatedAt=r.generated_at.isoformat(),
        )
        for r in rows
    ]
