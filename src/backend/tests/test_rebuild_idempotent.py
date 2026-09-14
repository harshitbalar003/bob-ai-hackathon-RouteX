"""
tests/test_rebuild_idempotent.py

Asserts that:
1. rebuild_derived is idempotent: running it twice produces the same excursion
   and gap rows (fingerprint match).
2. The sensor_readings composite index (shipment_id, timestamp) is used by the
   hot-path query — asserted via EXPLAIN QUERY PLAN output.
"""
from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio

from app.rebuild_derived import _fingerprint_derived, rebuild_derived


@pytest.mark.asyncio
async def test_rebuild_derived_idempotent() -> None:
    """
    Running rebuild_derived twice with the same raw readings must produce
    an identical result.  The fingerprint hashes the id, severity, degree_minutes,
    and peak_temp_c of every excursion + every gap's duration.
    """
    # First run
    await rebuild_derived()
    fp1 = await _fingerprint_derived()

    # Second run
    await rebuild_derived()
    fp2 = await _fingerprint_derived()

    assert fp1 == fp2, (
        f"rebuild_derived is NOT idempotent: fingerprint changed between runs.\n"
        f"  run 1: {fp1}\n"
        f"  run 2: {fp2}"
    )


@pytest.mark.asyncio
async def test_sensor_readings_index_used() -> None:
    """
    The composite index ix_sensor_readings_shipment_ts on (shipment_id, timestamp)
    must be used by the hot-path query:
        SELECT ... WHERE shipment_id = ? AND timestamp BETWEEN ? AND ? ORDER BY timestamp

    We assert this via SQLite EXPLAIN QUERY PLAN.
    With 500k readings, a table scan here is the difference between a responsive
    demo and a stalled one.
    """
    from datetime import datetime, timezone

    from sqlalchemy import text

    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        # Use a date range that exists in the seeded data
        result = await session.execute(
            text(
                "EXPLAIN QUERY PLAN "
                "SELECT id, temp_c, timestamp FROM sensor_readings "
                "WHERE shipment_id = 'shp-101' "
                "AND timestamp BETWEEN '2025-07-01T00:00:00Z' AND '2025-07-31T00:00:00Z' "
                "ORDER BY timestamp"
            )
        )
        rows = result.fetchall()

    # EXPLAIN QUERY PLAN should mention the index
    plan_text = " ".join(str(r) for r in rows).lower()

    assert "ix_sensor_readings_shipment_ts" in plan_text, (
        f"Expected composite index ix_sensor_readings_shipment_ts in query plan.\n"
        f"Got: {plan_text}\n"
        "This means the hot-path sensor query is doing a table scan — "
        "fix the index before the demo."
    )
