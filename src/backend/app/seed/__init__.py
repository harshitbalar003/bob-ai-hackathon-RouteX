"""
app/seed/__init__.py â€” Seed the SQLite database deterministically.

Exposes the public `seed()` coroutine and `_run_seed()` helper.
The `__main__.py` in this package handles `python -m app.seed`.

Usage:
    python -m app.seed           # uses seed=42 by default
    python -m app.seed --seed 42 # explicit seed

Running this twice with the same seed produces a byte-identical database
(given the same scenario YAML).  All timestamps are fixed to the scenario
anchor; all randomness flows through a seeded numpy.random.Generator.

Steps:
  1. Drop and recreate all tables
  2. Generate the world (nodes, lanes, shipments, fleet) from scenario YAML
  3. Insert all generated rows
  4. Generate telemetry for scripted cold-chain shipments
  5. Run rebuild_derived (excursions + gaps from raw readings)
  6. Run export_fixtures (write JSON fixtures to frontend)

Completes in under 15 seconds on a laptop.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import numpy as np

from app.database import AsyncSessionLocal, engine
from app.models.orm import Base, DisruptionRow
from app.seed.generate import generate_world, load_scenario
from app.seed.telemetry import generate_telemetry_for_shipment


async def _drop_and_recreate() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    print("  âœ“ Tables dropped and recreated.")


async def _insert_nodes_lanes(session, world: dict) -> None:
    for row in world["nodes"]:
        session.add(row)
    for row in world["lanes"]:
        session.add(row)
    print(f"  âœ“ {len(world['nodes'])} network nodes, {len(world['lanes'])} lanes.")


async def _insert_shipments(session, world: dict) -> None:
    for row in world["shipments"]:
        session.add(row)
    print(f"  âœ“ {len(world['shipments'])} shipments.")


async def _insert_fleet(session, world: dict) -> None:
    for row in world["fleet"]:
        session.add(row)
    for row in world["redeployment_matches"]:
        session.add(row)
    for row in world["reroute_options"]:
        session.add(row)
    print(
        f"  âœ“ {len(world['fleet'])} fleet assets, "
        f"{len(world['redeployment_matches'])} redeployment matches, "
        f"{len(world['reroute_options'])} reroute options."
    )


async def _insert_disruptions(session, scenario: dict, anchor: datetime) -> None:
    rows_inserted = 0
    for dis in scenario["disruptions"]:
        started_at = anchor + timedelta(hours=dis["started_at_offset_h"])

        if dis.get("expected_resolution_at") is None and "expected_resolution_at_offset_h" not in dis:
            expected_res = None
        elif "expected_resolution_at_offset_h" in dis:
            expected_res = anchor + timedelta(hours=dis["expected_resolution_at_offset_h"])
        else:
            expected_res = None

        area_yaml = dis["area"]
        if "radius_km" in area_yaml:
            area_data = {
                "center": area_yaml["center"],
                "radiusKm": area_yaml["radius_km"],
            }
        else:
            area_data = {"polygon": area_yaml["polygon"]}

        data = {
            "id": dis["id"],
            "type": dis["type"],
            "headline": dis["headline"],
            "detail": dis["detail"].strip(),
            "severity": dis["severity"],
            "startedAt": started_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "expectedResolutionAt": expected_res.strftime("%Y-%m-%dT%H:%M:%SZ") if expected_res else None,
            "confidence": dis["confidence"],
            "source": dis["source"],
            "affectedArea": area_data,
            "affectedNodes": dis.get("affected_nodes", []),
        }

        row = DisruptionRow(
            id=dis["id"],
            type=dis["type"],
            severity=dis["severity"],
            confidence=dis["confidence"],
            started_at=started_at,
            expected_resolution_at=expected_res,
            active=True,
            data=data,
        )
        session.add(row)
        rows_inserted += 1

    print(f"  âœ“ {rows_inserted} disruptions.")


async def _insert_telemetry(
    session,
    scenario: dict,
    world: dict,
    rng,
) -> None:
    """Generate and insert sensor readings + gaps for all scripted cold-chain shipments."""
    scripted_rows = {r.id: r for r in world["shipments"] if r.is_cold_chain}

    total_readings = 0
    total_gaps = 0

    for spec in scenario["scripted_shipments"]:
        ship_id = spec["id"]
        ship_row = scripted_rows.get(ship_id)
        if ship_row is None:
            print(f"  WARNING: scripted shipment {ship_id} not found in world rows")
            continue

        readings, gaps = generate_telemetry_for_shipment(spec, ship_row, rng)

        for r in readings:
            session.add(r)
        for g in gaps:
            session.add(g)

        total_readings += len(readings)
        total_gaps += len(gaps)

    print(f"  âœ“ {total_readings} sensor readings, {total_gaps} sensor gaps.")


async def seed(seed_value: int = 42) -> None:
    """Full seed pipeline. All steps are deterministic given seed_value."""
    t0 = time.perf_counter()
    print(f"\nSeeding database (seed={seed_value})â€¦")

    # â”€â”€ 1. Drop and recreate tables â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    await _drop_and_recreate()

    # â”€â”€ 2. Load scenario + generate world â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    scenario = load_scenario("storm_rotterdam")
    scenario["meta"]["random_seed"] = seed_value

    anchor = datetime.fromisoformat(
        scenario["meta"]["scenario_anchor_utc"].replace("Z", "+00:00")
    )

    rng = np.random.default_rng(seed_value)
    world = generate_world(scenario, rng)

    # â”€â”€ 3. Insert all rows in one transaction â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await _insert_nodes_lanes(session, world)
            await _insert_disruptions(session, scenario, anchor)
            await _insert_shipments(session, world)
            await _insert_fleet(session, world)
            telemetry_rng = np.random.default_rng(seed_value + 1)
            await _insert_telemetry(session, scenario, world, telemetry_rng)

    t1 = time.perf_counter()
    print(f"\n  World generation + insert: {t1 - t0:.1f}s")

    # â”€â”€ 4. rebuild_derived: excursions + gaps from raw readings â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    print("\nRunning rebuild_derivedâ€¦")
    from app.rebuild_derived import rebuild_derived
    await rebuild_derived()
    t2 = time.perf_counter()
    print(f"  rebuild_derived: {t2 - t1:.1f}s")

    # â”€â”€ 5. export_fixtures: write JSON fixtures to frontend â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    print("\nExporting fixturesâ€¦")
    from app.export_fixtures import export_fixtures
    await export_fixtures()
    t3 = time.perf_counter()
    print(f"  export_fixtures: {t3 - t2:.1f}s")

    print(f"\nâœ…  Seed complete in {t3 - t0:.1f}s total.\n")


# Expose for __main__.py
_run_seed = seed

