"""
app/seed.py — Seed the SQLite database from frontend fixture files.

Usage:
    python -m app.seed

Runs in under 10 seconds. Idempotent: drops and recreates all tables.
No credentials required.
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import sys
from datetime import datetime, timezone

from sqlalchemy import text

from app.database import AsyncSessionLocal, create_tables, engine
from app.models.orm import (
    Base,
    DisruptionRow,
    ExcursionRow,
    FleetAssetRow,
    RedeploymentMatchRow,
    RerouteOptionRow,
    SensorGapRow,
    SensorReadingRow,
    ShipmentRow,
)

# Path to the frontend fixtures — relative to this file's location
_FIXTURES = (
    pathlib.Path(__file__).parent.parent.parent  # src/
    / "frontend"
    / "src"
    / "data"
    / "fixtures"
)


def _load(filename: str) -> list[dict]:
    path = _FIXTURES / filename
    if not path.exists():
        print(f"  WARNING: fixture not found: {path}", file=sys.stderr)
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_dt(s: str | None) -> datetime | None:
    if s is None:
        return None
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _reading_id(shipment_id: str, sensor_id: str, timestamp: str) -> str:
    """Canonical reading ID: {shipmentId}:{sensorId}:{timestamp_ms}"""
    dt = _parse_dt(timestamp)
    ts_ms = int(dt.timestamp() * 1000)
    return f"{shipment_id}:{sensor_id}:{ts_ms}"


async def _drop_and_recreate() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    print("  Tables dropped and recreated.")


async def _seed_shipments(session) -> None:
    rows = _load("shipments.json")
    for raw in rows:
        cargo = raw.get("cargo", {})
        row = ShipmentRow(
            id=raw["id"],
            reference=raw["reference"],
            shipper=raw["shipper"],
            consignee=raw["consignee"],
            status=raw["status"],
            risk_score=raw.get("riskScore", 0),
            eta_original=_parse_dt(raw["etaOriginal"]),
            eta_projected=_parse_dt(raw["etaProjected"]),
            is_cold_chain=cargo.get("isColdChain", False),
            regulatory_regime=cargo.get("regulatoryRegime"),
            cargo_value_usd=cargo.get("valueUsd", 0),
            impacted_by=raw.get("impactedBy", []),
            data=raw,
        )
        session.add(row)
    print(f"  Seeded {len(rows)} shipments.")


async def _seed_disruptions(session) -> None:
    rows = _load("disruptions.json")
    for raw in rows:
        row = DisruptionRow(
            id=raw["id"],
            type=raw["type"],
            severity=raw["severity"],
            confidence=raw["confidence"],
            started_at=_parse_dt(raw["startedAt"]),
            expected_resolution_at=_parse_dt(raw.get("expectedResolutionAt")),
            active=True,
            data=raw,
        )
        session.add(row)
    print(f"  Seeded {len(rows)} disruptions.")


async def _seed_sensor_readings(session) -> None:
    rows = _load("sensor-readings.json")
    seen: set[str] = set()
    inserted = 0
    for raw in rows:
        rid = _reading_id(raw["shipmentId"], raw["sensorId"], raw["timestamp"])
        if rid in seen:
            continue  # deduplicate
        seen.add(rid)
        row = SensorReadingRow(
            id=rid,
            shipment_id=raw["shipmentId"],
            sensor_id=raw["sensorId"],
            leg_id=raw["legId"],
            timestamp=_parse_dt(raw["timestamp"]),
            temp_c=raw["tempC"],
            humidity_pct=raw.get("humidityPct"),
            door_open=raw.get("doorOpen"),
        )
        session.add(row)
        inserted += 1
    print(f"  Seeded {inserted} sensor readings ({len(rows) - inserted} duplicates skipped).")


async def _seed_sensor_gaps(session) -> None:
    rows = _load("sensor-gaps.json")
    for raw in rows:
        row = SensorGapRow(
            shipment_id=raw["shipmentId"],
            sensor_id=raw["sensorId"],
            leg_id=raw["legId"],
            gap_start_at=_parse_dt(raw["gapStartAt"]),
            gap_end_at=_parse_dt(raw["gapEndAt"]),
            duration_minutes=raw["durationMinutes"],
        )
        session.add(row)
    print(f"  Seeded {len(rows)} sensor gaps.")


async def _seed_excursions(session) -> None:
    rows = _load("excursions.json")
    for raw in rows:
        # evidence_reading_ids in fixture are timestamps — normalise to canonical IDs
        # We derive the shipment/sensor from the excursion's shipmentId and legId,
        # but the fixture doesn't carry sensorId on the excursion itself.
        # Store the raw timestamps for now; the engine will resolve to canonical IDs
        # when it reprocesses sensor readings.
        evidence_ids = raw.get("evidenceReadingIds", [])

        row = ExcursionRow(
            id=raw["id"],
            shipment_id=raw["shipmentId"],
            leg_id=raw["legId"],
            started_at=_parse_dt(raw["startedAt"]),
            ended_at=_parse_dt(raw.get("endedAt")),
            severity=raw["severity"],
            disposition=raw["disposition"],
            detected_before_delivery=raw["detectedBeforeDelivery"],
            degree_minutes=raw["degreeMinutes"],
            minutes_out_of_range=raw["minutesOutOfRange"],
            peak_temp_c=raw["peakTempC"],
            mean_kinetic_temp_c=raw["meanKineticTempC"],
            rule_pack_id="",        # populated by engine when reprocessed
            rule_id="",
            citation=raw.get("regulatoryBasis", ""),
            evidence_reading_ids=evidence_ids,
            data=raw,
        )
        session.add(row)
    print(f"  Seeded {len(rows)} excursions.")


async def _seed_fleet(session) -> None:
    rows = _load("fleet.json")
    for raw in rows:
        cap = raw.get("capacity", {})
        row = FleetAssetRow(
            id=raw["id"],
            type=raw["type"],
            status=raw["status"],
            reefer_capable=raw.get("reeferCapable", False),
            idle_since_hours=raw.get("idleSinceHours", 0),
            capacity_value=cap.get("value", 0),
            capacity_unit=cap.get("unit", "pallets"),
            home_depot=raw.get("homeDepot", ""),
            data=raw,
        )
        session.add(row)
    print(f"  Seeded {len(rows)} fleet assets.")


async def _seed_redeployment_matches(session) -> None:
    rows = _load("redeployment-matches.json")
    for raw in rows:
        row = RedeploymentMatchRow(
            asset_id=raw["assetId"],
            shipment_id=raw["shipmentId"],
            distance_km=raw["distanceKm"],
            hours_to_position=raw["hoursToPosition"],
            utilisation_gain_pct=raw["utilisationGainPct"],
            rationale=raw["rationale"],
            generated_at=_parse_dt(raw["generatedAt"]),
        )
        session.add(row)
    print(f"  Seeded {len(rows)} redeployment matches.")


async def _seed_reroute_options(session) -> None:
    rows = _load("reroute-options.json")
    for raw in rows:
        row = RerouteOptionRow(
            id=raw["id"],
            shipment_id=raw["shipmentId"],
            feasibility=raw["feasibility"],
            cold_chain_continuity=raw["coldChainContinuity"],
            recommended=raw.get("recommended", False),
            delta_days=raw.get("deltaDays", 0),
            delta_cost_usd=raw.get("deltaCostUsd", 0),
            data=raw,
        )
        session.add(row)
    print(f"  Seeded {len(rows)} reroute options.")


async def seed() -> None:
    print("Seeding database…")
    await _drop_and_recreate()
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await _seed_shipments(session)
            await _seed_disruptions(session)
            await _seed_sensor_readings(session)
            await _seed_sensor_gaps(session)
            await _seed_excursions(session)
            await _seed_fleet(session)
            await _seed_redeployment_matches(session)
            await _seed_reroute_options(session)
    print("Done. Database ready.")


if __name__ == "__main__":
    asyncio.run(seed())
