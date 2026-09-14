"""
app/export_fixtures.py â€” Export the seeded database to frontend fixture JSON files.

Writes to src/frontend/src/data/fixtures/ so both the mock adapter and the
API adapter render identical data.  Run automatically as the last step of
python -m app.seed.

Sensor readings are downsampled:
  - Every reading inside or within 30 min of an excursion window: kept
  - Elsewhere: one reading per 15 minutes (every 3rd reading at 5-min intervals)

This reduces the sensor-readings.json fixture from ~27k to ~4-6k rows while
preserving the shape that excursion charts need.  A metadata comment is written
to the file header so nobody mistakes the downsampled fixture for source data.

Usage:
    python -m app.export_fixtures
"""
from __future__ import annotations

import asyncio
import json
import pathlib
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.orm import (
    DisruptionRow,
    ExcursionRow,
    FleetAssetRow,
    RedeploymentMatchRow,
    RerouteOptionRow,
    SensorGapRow,
    SensorReadingRow,
    ShipmentRow,
)

_FIXTURES_DIR = (
    pathlib.Path(__file__).parent.parent.parent  # src/
    / "frontend"
    / "src"
    / "data"
    / "fixtures"
)

_DOWNSAMPLE_INTERVAL = 3     # keep every 3rd reading outside excursion windows
_EXCURSION_BUFFER_MIN = 30   # keep readings within this many minutes of excursion


def _write(filename: str, data: object, meta: dict | None = None) -> None:
    _FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    path = _FIXTURES_DIR / filename
    payload = data
    if meta:
        # Wrap arrays in an object with metadata (only for large files)
        # For consistency with the existing adapter, we only do this for
        # sensor-readings.json which the mock adapter reads directly as an array.
        # We add a top-level comment instead â€” JSON doesn't support comments, so
        # we write a companion meta file.
        meta_path = _FIXTURES_DIR / f"{filename}.meta.json"
        meta_path.write_text(
            json.dumps(meta, indent=2, default=str), encoding="utf-8"
        )
    path.write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )
    n = len(payload) if isinstance(payload, list) else "object"
    print(f"  â†’ {filename}: {n} items")


def _row_to_shipment(row: ShipmentRow) -> dict:
    return row.data


def _row_to_disruption(row: DisruptionRow) -> dict:
    return row.data


def _row_to_fleet(row: FleetAssetRow) -> dict:
    return row.data


def _row_to_excursion(row: ExcursionRow) -> dict:
    data = row.data.copy()
    # Ensure the canonical fields are present (some may come from engine output)
    data.setdefault("id", row.id)
    data.setdefault("shipmentId", row.shipment_id)
    data.setdefault("legId", row.leg_id)
    data["startedAt"] = row.started_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    data["endedAt"] = row.ended_at.strftime("%Y-%m-%dT%H:%M:%SZ") if row.ended_at else None
    data["severity"] = row.severity
    data["disposition"] = row.disposition
    data["detectedBeforeDelivery"] = row.detected_before_delivery
    data["degreeMinutes"] = row.degree_minutes
    data["minutesOutOfRange"] = row.minutes_out_of_range
    data["peakTempC"] = row.peak_temp_c
    data["meanKineticTempC"] = row.mean_kinetic_temp_c
    data["regulatoryBasis"] = row.citation
    data["evidenceReadingIds"] = row.evidence_reading_ids
    return data


def _row_to_sensor_reading(row: SensorReadingRow) -> dict:
    return {
        "shipmentId": row.shipment_id,
        "sensorId": row.sensor_id,
        "legId": row.leg_id,
        "timestamp": row.timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tempC": row.temp_c,
        "humidityPct": row.humidity_pct,
        "doorOpen": row.door_open,
    }


def _row_to_sensor_gap(row: SensorGapRow) -> dict:
    return {
        "shipmentId": row.shipment_id,
        "sensorId": row.sensor_id,
        "legId": row.leg_id,
        "gapStartAt": row.gap_start_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "gapEndAt": row.gap_end_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "durationMinutes": row.duration_minutes,
    }


def _row_to_reroute(row: RerouteOptionRow) -> dict:
    return row.data


def _row_to_redeploy(row: RedeploymentMatchRow) -> dict:
    return {
        "assetId": row.asset_id,
        "shipmentId": row.shipment_id,
        "distanceKm": row.distance_km,
        "hoursToPosition": row.hours_to_position,
        "utilisationGainPct": row.utilisation_gain_pct,
        "rationale": row.rationale,
        "generatedAt": row.generated_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _downsample_readings(
    readings: list[SensorReadingRow],
    excursion_rows: list[ExcursionRow],
    buffer_min: int = _EXCURSION_BUFFER_MIN,
    interval: int = _DOWNSAMPLE_INTERVAL,
) -> list[SensorReadingRow]:
    """
    Keep all readings within buffer_min of an excursion window.
    Downsample the rest to every `interval`-th reading.

    Note in fixture metadata: downsampled outside excursion windows.
    Source data in the database is not modified.
    """
    if not excursion_rows:
        # No excursions: uniform downsample
        return readings[::interval]

    # Build set of timestamps to always keep (inside + buffer of any excursion)
    keep_ts: set[datetime] = set()
    buffer = timedelta(minutes=buffer_min)
    for exc in excursion_rows:
        exc_start = exc.started_at - buffer
        exc_end = (exc.ended_at or (exc.started_at + timedelta(hours=4))) + buffer
        for r in readings:
            if exc_start <= r.timestamp <= exc_end:
                keep_ts.add(r.timestamp)

    result: list[SensorReadingRow] = []
    for idx, r in enumerate(readings):
        if r.timestamp in keep_ts:
            result.append(r)
        elif idx % interval == 0:
            result.append(r)

    return result


async def export_fixtures() -> None:
    """Read the seeded database and write all fixture JSON files."""
    print("Exporting fixtures to frontend/src/data/fixtures/")

    async with AsyncSessionLocal() as session:
        # â”€â”€ Shipments â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        shp_result = await session.execute(select(ShipmentRow))
        shipment_rows = shp_result.scalars().all()
        shipments = [_row_to_shipment(r) for r in shipment_rows]

        # â”€â”€ Disruptions â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        dis_result = await session.execute(
            select(DisruptionRow).where(DisruptionRow.active == True)
        )
        disruption_rows = dis_result.scalars().all()
        disruptions = [_row_to_disruption(r) for r in disruption_rows]

        # â”€â”€ Fleet â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        fleet_result = await session.execute(select(FleetAssetRow))
        fleet_rows = fleet_result.scalars().all()
        fleet = [_row_to_fleet(r) for r in fleet_rows]

        # â”€â”€ Excursions â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        exc_result = await session.execute(
            select(ExcursionRow).order_by(ExcursionRow.started_at)
        )
        excursion_rows = exc_result.scalars().all()
        excursions = [_row_to_excursion(r) for r in excursion_rows]

        # â”€â”€ Sensor gaps â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        gap_result = await session.execute(
            select(SensorGapRow).order_by(SensorGapRow.gap_start_at)
        )
        gap_rows = gap_result.scalars().all()
        sensor_gaps = [_row_to_sensor_gap(r) for r in gap_rows]

        # â”€â”€ Sensor readings (downsampled) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        rdg_result = await session.execute(
            select(SensorReadingRow)
            .where(
                SensorReadingRow.shipment_id.in_(
                    [r.shipment_id for r in excursion_rows]
                    or ["__none__"]
                )
            )
            .order_by(SensorReadingRow.shipment_id, SensorReadingRow.timestamp)
        )
        all_cold_readings = rdg_result.scalars().all()
        # Also get readings for cold chain shipments without excursions
        # (shp-102, shp-106 have no excursions but still need a trace)
        cold_chain_ids = {r.id for r in shipment_rows if r.is_cold_chain}
        if cold_chain_ids:
            all_rdg_result = await session.execute(
                select(SensorReadingRow)
                .where(SensorReadingRow.shipment_id.in_(cold_chain_ids))
                .order_by(SensorReadingRow.shipment_id, SensorReadingRow.timestamp)
            )
            all_cold_readings = all_rdg_result.scalars().all()

        downsampled = _downsample_readings(all_cold_readings, excursion_rows)
        sensor_readings = [_row_to_sensor_reading(r) for r in downsampled]

        # â”€â”€ Reroute options â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        reroute_result = await session.execute(
            select(RerouteOptionRow).order_by(
                RerouteOptionRow.recommended.desc(),
                RerouteOptionRow.delta_days,
            )
        )
        reroute_rows = reroute_result.scalars().all()
        reroutes = [_row_to_reroute(r) for r in reroute_rows]

        # â”€â”€ Redeployment matches â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        rdpl_result = await session.execute(
            select(RedeploymentMatchRow).order_by(RedeploymentMatchRow.hours_to_position)
        )
        rdpl_rows = rdpl_result.scalars().all()
        redeployments = [_row_to_redeploy(r) for r in rdpl_rows]

    # â”€â”€ Write files â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    _write("shipments.json", shipments)
    _write("disruptions.json", disruptions)
    _write("fleet.json", fleet)
    _write("excursions.json", excursions)
    _write("sensor-gaps.json", sensor_gaps)
    _write(
        "sensor-readings.json",
        sensor_readings,
        meta={
            "generated_by": "app/export_fixtures.py",
            "downsampled": True,
            "downsample_notes": (
                "All readings within 30 min of any excursion window are kept. "
                "Elsewhere: every 3rd reading (15-min sampling). "
                "Source data (5-min intervals) is in the database; "
                "this fixture is for UI rendering only."
            ),
        },
    )
    _write("reroute-options.json", reroutes)
    _write("redeployment-matches.json", redeployments)

    print(f"  âœ“ All fixtures written to {_FIXTURES_DIR}")


if __name__ == "__main__":
    asyncio.run(export_fixtures())

