"""
tests/test_phase1_smoke.py — Phase 1 smoke tests.

Validates: domain models, rule packs, ORM tables, seed data integrity.
"""
from __future__ import annotations

import asyncio
import json
import pathlib

import pytest

from app.models.domain import (
    Cargo,
    Decision,
    Disruption,
    Excursion,
    FleetAsset,
    GeoPoint,
    Leg,
    LegStatus,
    Mode,
    RegulatoryRegime,
    RulePack,
    Severity,
    Shipment,
    SensorReading,
    SeverityRule,
    TempRange,
)
from app.rules import get_rule_pack, load_rule_packs

_FIXTURES = (
    pathlib.Path(__file__).parent.parent.parent.parent  # d:\IBM_Safeguards
    / "src"
    / "frontend"
    / "src"
    / "data"
    / "fixtures"
)


# ─── Rule pack tests ──────────────────────────────────────────────────────────

def test_all_four_rule_packs_load():
    packs = load_rule_packs()
    assert set(packs.keys()) == {"GDP", "WHO_PQS", "USP_1079", "FSMA"}


def test_gdp_rule_pack_shape():
    pack = get_rule_pack("GDP")
    assert pack is not None
    assert pack.version == "1.0.0"
    assert pack.allowed_range_c.min == 2.0
    assert pack.allowed_range_c.max == 8.0
    assert len(pack.severity_rules) >= 3
    # First rule should be a critical freeze rule
    freeze_rules = [r for r in pack.severity_rules if r.below_range and r.severity == Severity.critical]
    assert len(freeze_rules) >= 1


def test_who_pqs_freeze_sensitive_has_zero_degree_minute_floor():
    """WHO PQS: even momentary freeze is critical for freeze-sensitive vaccines."""
    pack = get_rule_pack("WHO_PQS")
    assert pack is not None
    rule = next(
        (r for r in pack.severity_rules if r.id == "WHO-CRITICAL-FREEZE-SENSITIVE"),
        None,
    )
    assert rule is not None
    assert rule.below_range is True
    assert rule.min_degree_minutes == 0.0


def test_fsma_has_correct_temp_range():
    """FSMA refrigerated food: max 4°C."""
    pack = get_rule_pack("FSMA")
    assert pack is not None
    assert pack.allowed_range_c.max == 4.0


def test_usp_controlled_room_temp_range():
    pack = get_rule_pack("USP_1079")
    assert pack is not None
    assert pack.allowed_range_c.min == 15.0
    assert pack.allowed_range_c.max == 30.0


def test_rule_packs_have_disposition_maps():
    for pack in load_rule_packs().values():
        assert "critical" in pack.disposition_map
        assert "minor" in pack.disposition_map


# ─── Domain model tests ───────────────────────────────────────────────────────

def test_sensor_reading_canonical_id():
    r = SensorReading(
        shipmentId="shp-101",
        sensorId="sen-101-a",
        legId="leg-101-1",
        timestamp="2025-07-13T22:00:00.000Z",
        tempC=4.5,
    )
    rid = r.reading_id
    assert rid.startswith("shp-101:sen-101-a:")
    # Should be deterministic
    assert rid == r.reading_id


def test_regulatory_regime_no_none_member():
    """'NONE' was removed from the enum — verify it cannot be set."""
    members = {m.value for m in RegulatoryRegime}
    assert "NONE" not in members
    assert "GDP" in members
    assert "FSMA" in members


def test_cargo_regulatory_regime_optional():
    """regulatoryRegime is optional — absence means no regime."""
    cargo = Cargo(
        description="Automotive parts",
        valueUsd=380000,
        isColdChain=False,
    )
    assert cargo.regulatory_regime is None


def test_severity_enum_order():
    """Verify all four severity levels exist."""
    assert {s.value for s in Severity} == {"informational", "minor", "major", "critical"}


# ─── Fixture integrity tests ──────────────────────────────────────────────────

def test_fixture_shipments_load():
    """120 shipments in fixture; shp-101 to shp-106 are cold chain."""
    data = json.loads((_FIXTURES / "shipments.json").read_text())
    assert len(data) == 120
    cold_chain_ids = {s["id"] for s in data if s["cargo"]["isColdChain"]}
    for cc_id in ["shp-101", "shp-102", "shp-103", "shp-104", "shp-105", "shp-106"]:
        assert cc_id in cold_chain_ids, f"{cc_id} should be cold chain"


def test_fixture_disruptions_three():
    data = json.loads((_FIXTURES / "disruptions.json").read_text())
    assert len(data) == 3
    ids = {d["id"] for d in data}
    assert ids == {"dis-001", "dis-002", "dis-003"}


def test_fixture_dis003_low_confidence():
    """dis-003 is at 55% confidence — must not be presented as settled fact."""
    data = json.loads((_FIXTURES / "disruptions.json").read_text())
    dis003 = next(d for d in data if d["id"] == "dis-003")
    assert dis003["confidence"] == 0.55
    assert dis003["confidence"] < 0.6


def test_fixture_excursions_evidence_ids_present():
    """Every excursion has at least one evidence reading ID."""
    data = json.loads((_FIXTURES / "excursions.json").read_text())
    for exc in data:
        assert len(exc["evidenceReadingIds"]) > 0, f"{exc['id']} has no evidence IDs"


def test_fixture_sensor_gap():
    """Exactly one gap: shp-105, 215 minutes."""
    data = json.loads((_FIXTURES / "sensor-gaps.json").read_text())
    assert len(data) == 1
    gap = data[0]
    assert gap["shipmentId"] == "shp-105"
    assert gap["durationMinutes"] == 215


def test_fixture_fleet_first_18_idle():
    """First 18 fleet assets are idle."""
    data = json.loads((_FIXTURES / "fleet.json").read_text())
    idle = [a for a in data if a["status"] == "idle"]
    assert len(idle) >= 18
