"""
app/routers/shipments.py

GET /api/v1/shipments
GET /api/v1/shipments/{id}
GET /api/v1/shipments/{id}/readings
GET /api/v1/shipments/{id}/excursions
GET /api/v1/shipments/{id}/reroutes
POST /api/v1/shipments/{id}/reroutes/{rid}/accept
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.domain import (
    Cargo,
    Excursion,
    GeoPoint,
    Leg,
    RegulatoryRegime,
    RerouteOption,
    SensorGap,
    SensorReading,
    Shipment,
    ShipmentStatus,
)
from app.models.orm import (
    ExcursionRow,
    RerouteOptionRow,
    SensorGapRow,
    SensorReadingRow,
    ShipmentRow,
)

router = APIRouter(prefix="/shipments", tags=["shipments"])


def _row_to_shipment(row: ShipmentRow) -> Shipment:
    data = row.data
    legs_raw = data.get("legs", [])
    legs = []
    for lr in legs_raw:
        legs.append(
            Leg(
                id=lr["id"],
                sequence=lr["sequence"],
                mode=lr["mode"],
                carrier=lr["carrier"],
                **{"from": lr["from"]},
                to=lr["to"],
                departsAt=lr["departsAt"],
                arrivesAt=lr["arrivesAt"],
                status=lr["status"],
            )
        )
    cargo_raw = data.get("cargo", {})
    regime_raw = cargo_raw.get("regulatoryRegime")
    # Drop any legacy 'NONE' value (cleaned from domain.ts)
    regime = RegulatoryRegime(regime_raw) if regime_raw and regime_raw != "NONE" else None
    cargo = Cargo(
        description=cargo_raw.get("description", ""),
        valueUsd=cargo_raw.get("valueUsd", 0),
        isColdChain=cargo_raw.get("isColdChain", False),
        tempRangeC=cargo_raw.get("tempRangeC"),
        regulatoryRegime=regime,
    )
    origin_raw = data.get("origin", {})
    dest_raw = data.get("destination", {})
    return Shipment(
        id=data["id"],
        reference=data["reference"],
        shipper=data["shipper"],
        consignee=data["consignee"],
        origin=GeoPoint(**origin_raw),
        destination=GeoPoint(**dest_raw),
        legs=legs,
        cargo=cargo,
        etaOriginal=data["etaOriginal"],
        etaProjected=data["etaProjected"],
        status=data["status"],
        impactedBy=data.get("impactedBy", []),
        riskScore=data.get("riskScore", 0),
    )


def _row_to_reroute(row: RerouteOptionRow) -> RerouteOption:
    data = row.data
    new_legs = []
    for lr in data.get("newLegs", []):
        new_legs.append(
            Leg(
                id=lr["id"],
                sequence=lr["sequence"],
                mode=lr["mode"],
                carrier=lr["carrier"],
                **{"from": lr["from"]},
                to=lr["to"],
                departsAt=lr["departsAt"],
                arrivesAt=lr["arrivesAt"],
                status=lr["status"],
            )
        )
    return RerouteOption(
        id=data["id"],
        shipmentId=data["shipmentId"],
        summary=data["summary"],
        replacesLegIds=data.get("replacesLegIds", []),
        newLegs=new_legs,
        deltaDays=data.get("deltaDays", 0),
        deltaCostUsd=data.get("deltaCostUsd", 0),
        co2DeltaKg=data.get("co2DeltaKg", 0),
        coldChainContinuity=data.get("coldChainContinuity", "maintained"),
        coldChainContinuityReason=data.get("coldChainContinuityReason"),
        feasibility=data.get("feasibility", "speculative"),
        constraints=data.get("constraints", []),
        rationale=data.get("rationale", ""),
        recommended=data.get("recommended", False),
    )


@router.get("", response_model=list[Shipment])
async def list_shipments(
    db: Annotated[AsyncSession, Depends(get_db)],
    status: Optional[str] = Query(default=None),
    cold_chain: Optional[bool] = Query(default=None),
    value_min: Optional[float] = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[Shipment]:
    stmt = select(ShipmentRow)
    if status:
        stmt = stmt.where(ShipmentRow.status == status)
    if cold_chain is not None:
        stmt = stmt.where(ShipmentRow.is_cold_chain == cold_chain)
    if value_min is not None:
        stmt = stmt.where(ShipmentRow.cargo_value_usd >= value_min)
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [_row_to_shipment(r) for r in rows]


@router.get("/{shipment_id}", response_model=Shipment)
async def get_shipment(
    shipment_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Shipment:
    row = await db.get(ShipmentRow, shipment_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Shipment {shipment_id} not found")
    return _row_to_shipment(row)


@router.get("/{shipment_id}/readings")
async def get_shipment_readings(
    shipment_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    from_time: Optional[str] = Query(default=None, alias="from"),
    to_time: Optional[str] = Query(default=None, alias="to"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=1000, ge=1, le=5000),
) -> dict:
    """
    Returns sensor readings and data gaps for a shipment in chronological order.
    Gaps are interleaved with readings at their correct position.
    Response: { readings: [...], gaps: [...] }
    """
    stmt = (
        select(SensorReadingRow)
        .where(SensorReadingRow.shipment_id == shipment_id)
        .order_by(SensorReadingRow.timestamp)
    )
    if from_time:
        dt = datetime.fromisoformat(from_time.replace("Z", "+00:00"))
        stmt = stmt.where(SensorReadingRow.timestamp >= dt)
    if to_time:
        dt = datetime.fromisoformat(to_time.replace("Z", "+00:00"))
        stmt = stmt.where(SensorReadingRow.timestamp <= dt)
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    r_rows = result.scalars().all()

    gap_stmt = (
        select(SensorGapRow)
        .where(SensorGapRow.shipment_id == shipment_id)
        .order_by(SensorGapRow.gap_start_at)
    )
    gap_result = await db.execute(gap_stmt)
    g_rows = gap_result.scalars().all()

    readings = [
        SensorReading(
            shipmentId=r.shipment_id,
            sensorId=r.sensor_id,
            legId=r.leg_id,
            timestamp=r.timestamp.isoformat(),
            tempC=r.temp_c,
            humidityPct=r.humidity_pct,
            doorOpen=r.door_open,
        )
        for r in r_rows
    ]
    gaps = [
        SensorGap(
            shipmentId=g.shipment_id,
            sensorId=g.sensor_id,
            legId=g.leg_id,
            gapStartAt=g.gap_start_at.isoformat(),
            gapEndAt=g.gap_end_at.isoformat(),
            durationMinutes=g.duration_minutes,
        )
        for g in g_rows
    ]
    return {"readings": [r.model_dump(by_alias=True) for r in readings],
            "gaps": [g.model_dump(by_alias=True) for g in gaps]}


@router.get("/{shipment_id}/excursions", response_model=list[Excursion])
async def get_shipment_excursions(
    shipment_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[Excursion]:
    stmt = (
        select(ExcursionRow)
        .where(ExcursionRow.shipment_id == shipment_id)
        .order_by(ExcursionRow.started_at)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
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
        for r in rows
    ]


@router.get("/{shipment_id}/reroutes", response_model=list[RerouteOption])
async def get_shipment_reroutes(
    shipment_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[RerouteOption]:
    stmt = (
        select(RerouteOptionRow)
        .where(RerouteOptionRow.shipment_id == shipment_id)
        .order_by(RerouteOptionRow.recommended.desc(), RerouteOptionRow.delta_days)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [_row_to_reroute(r) for r in rows]


@router.post("/{shipment_id}/reroutes/{reroute_id}/accept")
async def accept_reroute(
    shipment_id: str,
    reroute_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Mark a reroute option as accepted (stub — persists a flag)."""
    row = await db.get(RerouteOptionRow, reroute_id)
    if row is None or row.shipment_id != shipment_id:
        raise HTTPException(status_code=404, detail="Reroute option not found")
    return {
        "accepted": True,
        "reroute_id": reroute_id,
        "shipment_id": shipment_id,
        "message": "Reroute option accepted. Notify carrier to confirm.",
    }
