"""
tests/test_impact.py — Impact engine tests.

Tests: leg geometry matching (cleared, mid-disruption, no geometry),
       circle vs polygon area, node matching, impact scoring, cascade legs.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.engines.impact import (
    assess_disruption_impact,
    haversine_km,
    leg_is_impacted,
    score_impact,
)
from app.models.domain import (
    AssetCapacity,
    Cargo,
    CircleArea,
    Disruption,
    DisruptionType,
    GeoPoint,
    Leg,
    LegStatus,
    Mode,
    PolygonArea,
    RegulatoryRegime,
    Severity,
    Shipment,
    ShipmentStatus,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

_NOW = datetime(2025, 7, 14, 12, 0, 0, tzinfo=timezone.utc)
_PAST = _NOW - timedelta(days=10)
_FUTURE = _NOW + timedelta(days=10)

_SHANGHAI = GeoPoint(lat=31.2, lng=121.5, label="Shanghai", unlocode="CNSGH")
_HAMBURG = GeoPoint(lat=53.55, lng=9.99, label="Hamburg", unlocode="DEHAM")
_ROTTERDAM = GeoPoint(lat=51.9, lng=4.48, label="Rotterdam", unlocode="NLRTM")
_SINGAPORE = GeoPoint(lat=1.29, lng=103.85, label="Singapore", unlocode="SGSIN")


def _leg(
    from_pt: GeoPoint,
    to_pt: GeoPoint,
    status: LegStatus = LegStatus.in_transit,
    departs_at: datetime | None = None,
    arrives_at: datetime | None = None,
    leg_id: str = "leg-001",
    seq: int = 1,
    mode: Mode = Mode.ocean,
) -> Leg:
    return Leg(
        id=leg_id,
        sequence=seq,
        mode=mode,
        carrier="Test Carrier",
        **{"from": from_pt.model_dump()},
        to=to_pt,
        departsAt=(departs_at or _PAST).isoformat(),
        arrivesAt=(arrives_at or _FUTURE).isoformat(),
        status=status,
    )


def _shipment(
    legs: list[Leg],
    value_usd: float = 500_000,
    is_cold_chain: bool = False,
    impacted_by: list[str] | None = None,
    shp_id: str = "shp-001",
) -> Shipment:
    return Shipment(
        id=shp_id,
        reference="SCL-TEST",
        shipper="Test Shipper",
        consignee="Test Consignee",
        origin=legs[0].from_,
        destination=legs[-1].to,
        legs=legs,
        cargo=Cargo(
            description="Test cargo",
            valueUsd=value_usd,
            isColdChain=is_cold_chain,
        ),
        etaOriginal=_FUTURE.isoformat(),
        etaProjected=_FUTURE.isoformat(),
        status=ShipmentStatus.on_track,
        impactedBy=impacted_by or [],
        riskScore=10,
    )


def _disruption_circle(
    center: GeoPoint = _SHANGHAI,
    radius_km: float = 800,
    severity: Severity = Severity.critical,
    confidence: float = 0.87,
    started_at: datetime | None = None,
    resolution: datetime | None = None,
) -> Disruption:
    return Disruption(
        id="dis-test",
        type=DisruptionType.weather,
        headline="Test disruption",
        detail="Test disruption detail",
        severity=severity,
        startedAt=(started_at or _NOW - timedelta(days=1)).isoformat(),
        expectedResolutionAt=resolution.isoformat() if resolution else None,
        confidence=confidence,
        source="Test",
        affectedArea=CircleArea(center=center, radiusKm=radius_km).model_dump(by_alias=True),
        affectedNodes=[center.unlocode] if center.unlocode else [],
    )


def _disruption_polygon(
    polygon: list[tuple[float, float]],
    affected_nodes: list[str],
    severity: Severity = Severity.major,
) -> Disruption:
    return Disruption(
        id="dis-poly",
        type=DisruptionType.labour_action,
        headline="Port strike",
        detail="Strike detail",
        severity=severity,
        startedAt=(_NOW - timedelta(days=1)).isoformat(),
        expectedResolutionAt=None,
        confidence=0.72,
        source="Test",
        affectedArea=PolygonArea(polygon=polygon).model_dump(),
        affectedNodes=affected_nodes,
    )


# ── Haversine tests ───────────────────────────────────────────────────────────

class TestHaversine:

    def test_same_point_zero(self):
        assert haversine_km(0, 0, 0, 0) == pytest.approx(0.0, abs=0.01)

    def test_known_distance_london_paris(self):
        """London (51.5°N, 0.1°W) to Paris (48.9°N, 2.4°E) ≈ 340 km."""
        d = haversine_km(51.5, -0.1, 48.9, 2.4)
        assert 330 < d < 360

    def test_known_distance_equator(self):
        """1° longitude on the equator ≈ 111 km."""
        d = haversine_km(0.0, 0.0, 0.0, 1.0)
        assert abs(d - 111.2) < 2.0


# ── Leg intersection tests ─────────────────────────────────────────────────────

class TestLegIntersection:

    def test_completed_leg_never_impacted(self):
        """A completed leg is NEVER impacted regardless of position."""
        leg = _leg(_SHANGHAI, _HAMBURG, status=LegStatus.completed)
        dis = _disruption_circle(_SHANGHAI, radius_km=800)
        assert leg_is_impacted(leg, dis) is False

    def test_in_transit_leg_through_affected_area(self):
        """In-transit leg passing through affected circle is impacted."""
        # Shanghai → Hamburg passes through/near Shanghai (radius 800km)
        leg = _leg(_SHANGHAI, _HAMBURG, status=LegStatus.in_transit)
        dis = _disruption_circle(_SHANGHAI, radius_km=800)
        assert leg_is_impacted(leg, dis) is True

    def test_leg_far_from_disruption(self):
        """Rotterdam → Hamburg leg is not impacted by Shanghai typhoon."""
        leg = _leg(_ROTTERDAM, _HAMBURG, status=LegStatus.in_transit)
        dis = _disruption_circle(_SHANGHAI, radius_km=800)
        assert leg_is_impacted(leg, dis) is False

    def test_leg_completes_before_disruption_starts(self):
        """Leg that finishes before disruption begins is not impacted."""
        leg = _leg(
            _SHANGHAI, _HAMBURG,
            status=LegStatus.in_transit,
            departs_at=_NOW - timedelta(days=5),
            arrives_at=_NOW - timedelta(days=1),   # arrives before disruption
        )
        dis = _disruption_circle(
            _SHANGHAI,
            started_at=_NOW,   # disruption starts after leg arrives
        )
        assert leg_is_impacted(leg, dis) is False

    def test_leg_starts_after_disruption_resolves(self):
        """Leg that starts after disruption resolves is not impacted."""
        leg = _leg(
            _SHANGHAI, _HAMBURG,
            status=LegStatus.scheduled,
            departs_at=_NOW + timedelta(days=5),
            arrives_at=_NOW + timedelta(days=30),
        )
        dis = _disruption_circle(
            _SHANGHAI,
            resolution=_NOW + timedelta(days=2),  # resolves before leg starts
        )
        assert leg_is_impacted(leg, dis) is False

    def test_polygon_area_node_match(self):
        """Leg terminating at an affectedNode is impacted (polygon area)."""
        # Rotterdam polygon from dis-002 fixture
        polygon = [
            (51.96, 4.02), (51.97, 4.18), (51.93, 4.22),
            (51.89, 4.25), (51.86, 4.15), (51.88, 4.00),
            (51.93, 3.97), (51.96, 4.02),
        ]
        dis = _disruption_polygon(polygon, affected_nodes=["NLRTM"])
        leg = _leg(_SINGAPORE, _ROTTERDAM, status=LegStatus.in_transit)
        assert leg_is_impacted(leg, dis) is True

    def test_polygon_area_path_through(self):
        """Leg path sampling intersects polygon."""
        # Large polygon centred on Atlantic — a transatlantic leg would cross it
        polygon = [
            (40.0, -40.0), (60.0, -40.0), (60.0, -20.0),
            (40.0, -20.0), (40.0, -40.0),
        ]
        dis = _disruption_polygon(polygon, affected_nodes=[])
        # Leg from Rotterdam (51.9°N, 4.5°E) to New York (40.7°N, -74°W)
        nyc = GeoPoint(lat=40.7, lng=-74.0, label="New York", unlocode="USNYC")
        leg = _leg(_ROTTERDAM, nyc, status=LegStatus.in_transit)
        assert leg_is_impacted(leg, dis) is True

    def test_scheduled_leg_in_affected_area_is_impacted(self):
        """A scheduled (not yet departed) leg is impacted if it passes through."""
        leg = _leg(
            _SHANGHAI, _HAMBURG,
            status=LegStatus.scheduled,
            departs_at=_NOW + timedelta(days=1),
            arrives_at=_NOW + timedelta(days=30),
        )
        dis = _disruption_circle(_SHANGHAI, radius_km=800)
        assert leg_is_impacted(leg, dis) is True


# ── Impact scoring tests ──────────────────────────────────────────────────────

class TestImpactScoring:

    def test_score_has_all_components(self):
        """ImpactScore includes all required component fields."""
        leg = _leg(_SHANGHAI, _HAMBURG)
        shp = _shipment([leg])
        dis = _disruption_circle(_SHANGHAI)
        score = score_impact(shp, dis, [leg])
        assert score.delay_hours > 0
        assert score.cargo_value_usd == 500_000
        assert isinstance(score.cold_chain_exposure, bool)
        assert score.total_score >= 0.0
        assert score.total_score <= 100.0

    def test_decision_attached(self):
        """Every ImpactScore has a Decision with evidence."""
        leg = _leg(_SHANGHAI, _HAMBURG)
        shp = _shipment([leg])
        dis = _disruption_circle(_SHANGHAI)
        score = score_impact(shp, dis, [leg])
        assert score.decision.rule_pack_id == "IMPACT_SCORING"
        assert score.decision.rule_id.startswith("IMPACT-")
        assert leg.id in score.decision.evidence_record_ids

    def test_cold_chain_exposure_increases_score(self):
        """Cold chain shipment with imminent delivery scores higher."""
        leg_normal = _leg(_SHANGHAI, _HAMBURG)
        leg_cold = _leg(_SHANGHAI, _HAMBURG)
        shp_normal = _shipment([leg_normal], is_cold_chain=False)
        shp_cold = _shipment([leg_cold], is_cold_chain=True)
        shp_cold = shp_cold.model_copy(
            update={"eta_projected": (_NOW + timedelta(hours=10)).isoformat()}
        )
        dis = _disruption_circle(_SHANGHAI)
        score_normal = score_impact(shp_normal, dis, [leg_normal])
        score_cold = score_impact(shp_cold, dis, [leg_cold])
        assert score_cold.total_score >= score_normal.total_score

    def test_critical_disruption_scores_higher_than_minor(self):
        """Critical disruption produces higher score than minor for same shipment."""
        leg = _leg(_SHANGHAI, _HAMBURG)
        shp = _shipment([leg])
        dis_critical = _disruption_circle(_SHANGHAI, severity=Severity.critical)
        dis_minor = _disruption_circle(_SHANGHAI, severity=Severity.minor)
        score_critical = score_impact(shp, dis_critical, [leg])
        score_minor = score_impact(shp, dis_minor, [leg])
        assert score_critical.total_score > score_minor.total_score

    def test_higher_value_cargo_scores_higher(self):
        """$1M cargo scores higher than $50K cargo under same disruption."""
        leg = _leg(_SHANGHAI, _HAMBURG)
        shp_high = _shipment([leg], value_usd=1_000_000)
        shp_low = _shipment([leg], value_usd=50_000, shp_id="shp-002")
        dis = _disruption_circle(_SHANGHAI)
        score_high = score_impact(shp_high, dis, [leg])
        score_low = score_impact(shp_low, dis, [leg])
        assert score_high.total_score > score_low.total_score


# ── assess_disruption_impact integration tests ────────────────────────────────

class TestAssessDisruptionImpact:

    def test_only_impacted_shipments_returned(self):
        """Only shipments with at least one incomplete impacted leg are returned."""
        # Leg near Shanghai (impacted by typhoon)
        leg_near = _leg(_SHANGHAI, _HAMBURG, leg_id="leg-near", status=LegStatus.in_transit)
        # Leg far from Shanghai (Rotterdam→Hamburg)
        leg_far = _leg(_ROTTERDAM, _HAMBURG, leg_id="leg-far", status=LegStatus.in_transit)

        shp_near = _shipment([leg_near], shp_id="shp-near")
        shp_far = _shipment([leg_far], shp_id="shp-far")

        dis = _disruption_circle(_SHANGHAI, radius_km=800)
        results = assess_disruption_impact(dis, [shp_near, shp_far])

        result_ids = {r.shipment_id for r in results}
        assert "shp-near" in result_ids
        assert "shp-far" not in result_ids

    def test_results_sorted_by_score_descending(self):
        """Results are sorted highest-score-first."""
        leg1 = _leg(_SHANGHAI, _HAMBURG, leg_id="leg-1")
        leg2 = _leg(_SHANGHAI, _HAMBURG, leg_id="leg-2")

        shp_high = _shipment([leg1], value_usd=1_000_000, shp_id="shp-high")
        shp_low = _shipment([leg2], value_usd=10_000, shp_id="shp-low")

        dis = _disruption_circle(_SHANGHAI)
        results = assess_disruption_impact(dis, [shp_high, shp_low])

        assert len(results) == 2
        assert results[0].total_score >= results[1].total_score

    def test_completed_leg_shipment_not_returned(self):
        """Shipment with only completed legs is not in results."""
        leg = _leg(_SHANGHAI, _HAMBURG, status=LegStatus.completed)
        shp = _shipment([leg])
        dis = _disruption_circle(_SHANGHAI)
        results = assess_disruption_impact(dis, [shp])
        assert len(results) == 0

    def test_empty_shipment_list(self):
        dis = _disruption_circle(_SHANGHAI)
        results = assess_disruption_impact(dis, [])
        assert results == []

    def test_cascade_legs_counted(self):
        """Cascade legs (after impacted leg) are counted in the score."""
        leg1 = _leg(_SHANGHAI, _SINGAPORE, leg_id="leg-1", seq=1, status=LegStatus.in_transit)
        leg2 = _leg(_SINGAPORE, _ROTTERDAM, leg_id="leg-2", seq=2, status=LegStatus.scheduled)
        leg3 = _leg(_ROTTERDAM, _HAMBURG, leg_id="leg-3", seq=3, status=LegStatus.scheduled)

        shp = _shipment([leg1, leg2, leg3])
        dis = _disruption_circle(_SHANGHAI, radius_km=800)
        results = assess_disruption_impact(dis, [shp])

        assert len(results) == 1
        # leg1 is impacted; legs 2 and 3 are cascade
        assert results[0].cascade_legs == 2
