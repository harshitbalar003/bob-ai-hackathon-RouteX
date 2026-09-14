"""
app/rebuild_derived.py -- Recompute all derived data from raw source rows.

Drops and recomputes:
  - excursions  (from sensor_readings + shipments + rule packs)
  - sensor_gaps (re-detected from sensor_readings)

Running this twice with the same raw data produces an identical result.
This is asserted by the test in tests/test_rebuild_idempotent.py.

Usage:
    python -m app.rebuild_derived
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import delete, select

from app.database import AsyncSessionLocal
from app.engines.cold_chain import analyse_leg
from app.models.domain import RegulatoryRegime, SensorReading
from app.models.orm import (
    ExcursionRow,
    SensorGapRow,
    SensorReadingRow,
    ShipmentRow,
)
from app.rules import load_rule_packs


def _to_domain_reading(r: SensorReadingRow) -> SensorReading:
    return SensorReading(
        shipmentId=r.shipment_id,
        sensorId=r.sensor_id,
        legId=r.leg_id,
        timestamp=r.timestamp,
        tempC=r.temp_c,
        humidityPct=r.humidity_pct,
        doorOpen=r.door_open,
    )


def _exc_to_json_safe(exc_model_dump: dict) -> dict:
    """Convert a Pydantic model_dump() to a JSON-safe dict (datetimes -> ISO strings)."""
    result = {}
    for k, v in exc_model_dump.items():
        if isinstance(v, datetime):
            result[k] = v.strftime("%Y-%m-%dT%H:%M:%SZ")
        elif isinstance(v, list):
            result[k] = [
                item.strftime("%Y-%m-%dT%H:%M:%SZ") if isinstance(item, datetime) else item
                for item in v
            ]
        else:
            result[k] = v
    return result


async def rebuild_derived() -> dict:
    """
    Drop and recompute excursions and sensor_gaps from raw readings.

    Returns a summary dict: {excursions_written, gaps_written}
    """
    rule_packs = load_rule_packs()

    async with AsyncSessionLocal() as session:
        async with session.begin():
            # Clear derived tables
            await session.execute(delete(ExcursionRow))
            await session.execute(delete(SensorGapRow))

            # Load cold-chain shipments
            stmt = select(ShipmentRow).where(ShipmentRow.is_cold_chain == True)
            result = await session.execute(stmt)
            cold_chain_rows = result.scalars().all()

            excursions_written = 0
            gaps_written = 0

            for ship_row in cold_chain_rows:
                regime_str = ship_row.regulatory_regime
                if not regime_str:
                    continue
                try:
                    regime = RegulatoryRegime(regime_str)
                except ValueError:
                    continue

                rule_pack = rule_packs.get(regime.value)
                if rule_pack is None:
                    continue

                legs_data = ship_row.data.get("legs", [])
                eta_projected_str = ship_row.data.get("etaProjected")
                delivery_eta = None
                if eta_projected_str:
                    try:
                        delivery_eta = datetime.fromisoformat(
                            eta_projected_str.replace("Z", "+00:00")
                        )
                    except (ValueError, AttributeError):
                        pass

                for leg_data in legs_data:
                    leg_id = leg_data["id"]
                    is_complete = leg_data.get("status") == "completed"

                    r_stmt = (
                        select(SensorReadingRow)
                        .where(SensorReadingRow.shipment_id == ship_row.id)
                        .where(SensorReadingRow.leg_id == leg_id)
                        .order_by(SensorReadingRow.timestamp)
                    )
                    r_result = await session.execute(r_stmt)
                    reading_rows = r_result.scalars().all()

                    if not reading_rows:
                        continue

                    domain_readings = [_to_domain_reading(r) for r in reading_rows]

                    excursion_results, gaps, sensor_suspect = analyse_leg(
                        readings=domain_readings,
                        rule_pack=rule_pack,
                        shipment_id=ship_row.id,
                        leg_id=leg_id,
                        cargo_description=ship_row.data.get("cargo", {}).get("description", ""),
                        is_leg_complete=is_complete,
                        delivery_eta=delivery_eta,
                    )

                    for exc_result in excursion_results:
                        exc = exc_result.excursion
                        decision = exc_result.decision
                        # Convert Pydantic model to JSON-safe dict
                        exc_data = _exc_to_json_safe(exc.model_dump(by_alias=True))
                        row = ExcursionRow(
                            id=exc.id,
                            shipment_id=exc.shipment_id,
                            leg_id=exc.leg_id,
                            started_at=exc.started_at,
                            ended_at=exc.ended_at,
                            severity=exc.severity.value,
                            disposition=exc.disposition.value,
                            detected_before_delivery=exc.detected_before_delivery,
                            degree_minutes=exc.degree_minutes,
                            minutes_out_of_range=exc.minutes_out_of_range,
                            peak_temp_c=exc.peak_temp_c,
                            mean_kinetic_temp_c=exc.mean_kinetic_temp_c,
                            rule_pack_id=decision.rule_pack_id,
                            rule_id=decision.rule_id,
                            citation=decision.citation,
                            evidence_reading_ids=exc.evidence_reading_ids,
                            data=exc_data,
                        )
                        session.add(row)
                        excursions_written += 1

                    for gap in gaps:
                        row = SensorGapRow(
                            shipment_id=gap.shipment_id,
                            sensor_id=gap.sensor_id,
                            leg_id=gap.leg_id,
                            gap_start_at=gap.gap_start_at,
                            gap_end_at=gap.gap_end_at,
                            duration_minutes=int(gap.duration_minutes),
                        )
                        session.add(row)
                        gaps_written += 1

    print(f"  [ok] rebuild_derived: {excursions_written} excursions, {gaps_written} gaps.")
    return {"excursions_written": excursions_written, "gaps_written": gaps_written}


async def _fingerprint_derived() -> str:
    """
    Compute a deterministic fingerprint of all derived rows.
    Used by the idempotency test to assert two runs produce identical output.
    """
    async with AsyncSessionLocal() as session:
        exc_result = await session.execute(
            select(ExcursionRow).order_by(ExcursionRow.id)
        )
        gap_result = await session.execute(
            select(SensorGapRow).order_by(
                SensorGapRow.shipment_id,
                SensorGapRow.gap_start_at,
            )
        )
        excursions = exc_result.scalars().all()
        gaps = gap_result.scalars().all()

    exc_payload = [
        {
            "id": e.id,
            "shipment_id": e.shipment_id,
            "leg_id": e.leg_id,
            "severity": e.severity,
            "disposition": e.disposition,
            "degree_minutes": round(e.degree_minutes, 4),
            "minutes_out_of_range": e.minutes_out_of_range,
            "peak_temp_c": round(e.peak_temp_c, 4),
        }
        for e in excursions
    ]
    gap_payload = [
        {
            "shipment_id": g.shipment_id,
            "sensor_id": g.sensor_id,
            "leg_id": g.leg_id,
            "duration_minutes": g.duration_minutes,
        }
        for g in gaps
    ]
    payload = json.dumps({"excursions": exc_payload, "gaps": gap_payload}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


if __name__ == "__main__":
    asyncio.run(rebuild_derived())
