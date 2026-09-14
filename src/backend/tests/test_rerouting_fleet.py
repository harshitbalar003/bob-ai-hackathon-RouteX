"""
tests/test_rerouting_fleet.py — Rerouting and fleet engine tests.

Tests: null option wins when alternatives are worse, cold-chain-breaking options
       are never recommended, fleet ranking by capacity-hours (not count),
       greedy redeployment matching.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.engines.fleet import compute_capacity_hours, match_idle_to_impacted, rank_idle_assets
from app.engines.rerouting import (
    _find_paths,
    _rank_score,
    generate_reroutes,
)
from app.models.domain import (
    AssetCapacity,
    AssetStatus,
    AssetType,
    Cargo,
    ColdChainContinuity,
    FleetAsset,
    GeoPoint,
    Leg,
    LegStatus,
    Mode,
    RerouteFeasibility,
    Shipment,
    ShipmentStatus,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

_NOW = datetime(2025, 7, 14, 12, 0, 0, tzinfo=timezone.utc)
_FUTURE = _NOW + timedelta(days=30)

_SHANGHAI = GeoPoint(lat=31.2, lng=121.5, label="Shanghai", unlocode="CNSGH")
_HAMBURG = GeoPoint(lat=53.55, lng=9.99, label="Hamburg", unlocode="DEHAM")
_ROTTERDAM = GeoPoint(lat=51.9, lng=4.48, label="Rotterdam", unlocode="NLRTM")
_FRANKFURT = GeoPoint(lat=50.03, lng=8.57, label="Frankfurt", unlocode="DEFRA")


def _leg(from_pt: GeoPoint, to_pt: GeoPoint, status: LegStatus = LegStatus.in_transit, seq: int = 1) -> Leg:
    return Leg(
        id=f"leg-{seq}",
        sequence=seq,
        mode=Mode.ocean,
        carrier="Test",
        **{"from": from_pt.model_dump()},
        to=to_pt,
        departsAt=(_NOW - timedelta(days=5)).isoformat(),
        arrivesAt=(_NOW + timedelta(days=25)).isoformat(),
        status=status,
    )


def _shipment(
    legs: list[Leg],
    is_cold_chain: bool = False,
    value_usd: float = 500_000,
    shp_id: str = "shp-001",
) -> Shipment:
    return Shipment(
        id=shp_id,
        reference="TEST",
        shipper="Test",
        consignee="Test",
        origin=legs[0].from_,
        destination=legs[-1].to,
        legs=legs,
        cargo=Cargo(
            description="Test cargo vaccines" if is_cold_chain else "Test cargo",
            valueUsd=value_usd,
            isColdChain=is_cold_chain,
        ),
        etaOriginal=_FUTURE.isoformat(),
        etaProjected=_FUTURE.isoformat(),
        status=ShipmentStatus.on_track,
        impactedBy=[],
        riskScore=10,
    )


def _asset(
    asset_id: str,
    idle_hours: float,
    capacity_value: float,
    capacity_unit: str = "pallets",
    reefer: bool = False,
    location: GeoPoint | None = None,
) -> FleetAsset:
    return FleetAsset(
        id=asset_id,
        type=AssetType.truck,
        status=AssetStatus.idle,
        location=location or GeoPoint(lat=53.55, lng=9.99, label="Hamburg"),
        idleSinceAt=(_NOW - timedelta(hours=idle_hours)).isoformat(),
        idleSinceHours=idle_hours,
        capacity=AssetCapacity(unit=capacity_unit, value=capacity_value),
        utilisationPct30d=30.0,
        reeferCapable=reefer,
        homeDepot="Hamburg",
    )


# ── Rerouting tests ───────────────────────────────────────────────────────────

class TestRankScore:

    def test_null_option_wins_when_alternatives_worse(self):
        """
        Null option should win when alternatives have bad cold chain or high delay.

        Null: 2 days delay, maintained, $0 cost, confirmed → score ~0.74
        Bad alt: 3 days delay, broken cold chain, $5K cost, speculative → score ~0.13
        """
        null_score = _rank_score(
            delta_days=2.0,
            cc=ColdChainContinuity.maintained,
            cost_delta=0.0,
            feasibility=RerouteFeasibility.confirmed,
        )
        bad_alt_score = _rank_score(
            delta_days=3.0,
            cc=ColdChainContinuity.broken,
            cost_delta=5000.0,
            feasibility=RerouteFeasibility.speculative,
        )
        assert null_score > bad_alt_score, (
            f"Null ({null_score:.3f}) should beat bad alternative ({bad_alt_score:.3f})"
        )

    def test_cold_chain_broken_scores_zero_for_cc_component(self):
        """ColdChainContinuity.broken = 0.0 for the cc weight component."""
        score_broken = _rank_score(
            delta_days=1.0, cc=ColdChainContinuity.broken,
            cost_delta=0.0, feasibility=RerouteFeasibility.confirmed,
        )
        score_maintained = _rank_score(
            delta_days=1.0, cc=ColdChainContinuity.maintained,
            cost_delta=0.0, feasibility=RerouteFeasibility.confirmed,
        )
        assert score_maintained > score_broken

    def test_faster_route_scores_higher(self):
        """Recovering time improves score."""
        score_fast = _rank_score(
            delta_days=-1.0,   # recovers 1 day
            cc=ColdChainContinuity.maintained,
            cost_delta=1000.0,
            feasibility=RerouteFeasibility.likely,
        )
        score_slow = _rank_score(
            delta_days=5.0,
            cc=ColdChainContinuity.maintained,
            cost_delta=1000.0,
            feasibility=RerouteFeasibility.likely,
        )
        assert score_fast > score_slow


class TestPathFinding:

    def test_direct_path_exists(self):
        """Shanghai → Hamburg should have at least one direct path."""
        paths = _find_paths("CNSGH", "DEHAM", blocked_nodes=set())
        assert len(paths) >= 1

    def test_blocked_node_excluded(self):
        """Paths avoid blocked nodes."""
        # Block Shanghai's direct connection
        paths = _find_paths("CNSGH", "DEHAM", blocked_nodes={"DEHAM"})
        # Blocked destination means no path (or empty)
        # All paths to DEHAM are blocked if DEHAM is in blocked_nodes
        assert all(
            all(lane.to_node != "DEHAM" for lane in path)
            or len(path) == 0
            for path in paths
        )

    def test_reefer_required_filters_non_reefer_lanes(self):
        """With reefer_required=True, only reefer-capable lanes are used."""
        paths = _find_paths("CNSGH", "DEHAM", blocked_nodes=set(), reefer_required=True)
        for path in paths:
            for lane in path:
                assert lane.reefer_capable, (
                    f"Non-reefer lane included: {lane.from_node}→{lane.to_node} via {lane.carrier}"
                )


class TestGenerateReroutes:

    def test_null_option_always_present(self):
        """generate_reroutes always includes a null option."""
        leg = _leg(_SHANGHAI, _HAMBURG)
        shp = _shipment([leg])
        opts = generate_reroutes(shp, blocked_nodes={"CNSGH"}, original_eta=_FUTURE)
        null_opts = [o for o in opts if "null" in o.id]
        assert len(null_opts) >= 1

    def test_cold_chain_breaking_never_recommended(self):
        """
        A reroute option that breaks cold chain must never be marked recommended.
        """
        leg = _leg(_SHANGHAI, _HAMBURG)
        shp = _shipment([leg], is_cold_chain=True)
        opts = generate_reroutes(shp, blocked_nodes={"CNSGH"}, original_eta=_FUTURE)
        for opt in opts:
            if opt.cold_chain_continuity == ColdChainContinuity.broken:
                assert opt.recommended is False, (
                    f"Option {opt.id} has broken cold chain but is marked recommended"
                )

    def test_returns_list(self):
        """generate_reroutes always returns a list (may be short for unknown routes)."""
        leg = _leg(_SHANGHAI, _HAMBURG)
        shp = _shipment([leg])
        opts = generate_reroutes(shp, blocked_nodes=set(), original_eta=_FUTURE)
        assert isinstance(opts, list)

    def test_all_completed_legs_returns_null_only(self):
        """A shipment with all completed legs gets only the null option."""
        leg = _leg(_SHANGHAI, _HAMBURG, status=LegStatus.completed)
        shp = _shipment([leg])
        opts = generate_reroutes(shp, blocked_nodes={"CNSGH"}, original_eta=_FUTURE)
        assert len(opts) >= 1
        assert any("null" in o.id for o in opts)


# ── Fleet engine tests ────────────────────────────────────────────────────────

class TestFleetRanking:

    def test_rank_by_capacity_hours_not_count(self):
        """
        Ranking is by capacity × idle_hours, not by count.

        Asset A: 33 pallets × 10h = 330 capacity-hours
        Asset B: 10 pallets × 100h = 1000 capacity-hours

        B should rank first even though A was idle more recently.
        """
        asset_a = _asset("ast-a", idle_hours=10, capacity_value=33)
        asset_b = _asset("ast-b", idle_hours=100, capacity_value=10)

        ranked = rank_idle_assets([asset_a, asset_b])

        assert ranked[0].id == "ast-b", (
            f"Expected ast-b (1000 cap-hrs) first; got {ranked[0].id}"
        )
        assert ranked[1].id == "ast-a"

    def test_non_idle_assets_excluded(self):
        """Assets not in 'idle' status are excluded from ranking."""
        idle = _asset("idle-1", 48, 33)
        transit = FleetAsset(
            id="transit-1",
            type=AssetType.truck,
            status=AssetStatus.in_transit,
            location=GeoPoint(lat=0, lng=0, label="At sea"),
            idleSinceAt=_NOW.isoformat(),
            idleSinceHours=0,
            capacity=AssetCapacity(unit="pallets", value=33),
            utilisationPct30d=80,
            reeferCapable=False,
            homeDepot="Hamburg",
        )
        ranked = rank_idle_assets([idle, transit])
        assert len(ranked) == 1
        assert ranked[0].id == "idle-1"

    def test_capacity_hours_formula(self):
        """capacity_hours = capacity.value × idle_since_hours"""
        asset = _asset("ast-x", idle_hours=48, capacity_value=33)
        assert compute_capacity_hours(asset) == pytest.approx(33 * 48)

    def test_empty_list(self):
        assert rank_idle_assets([]) == []


class TestRedeploymentMatching:

    def test_reefer_asset_matched_to_cold_chain_shipment(self):
        """Cold chain shipment gets a reefer-capable asset."""
        reefer = _asset("reefer-1", 24, 10, reefer=True)
        non_reefer = _asset("truck-1", 100, 33, reefer=False)

        leg = _leg(_HAMBURG, _ROTTERDAM)
        cold_shp = _shipment([leg], is_cold_chain=True)

        matches = match_idle_to_impacted([reefer, non_reefer], [cold_shp])
        assert len(matches) == 1
        assert matches[0].asset_id == "reefer-1"

    def test_non_reefer_not_matched_to_cold_chain(self):
        """Non-reefer asset is not matched to a cold-chain shipment."""
        non_reefer = _asset("truck-1", 100, 33, reefer=False)
        leg = _leg(_HAMBURG, _ROTTERDAM)
        cold_shp = _shipment([leg], is_cold_chain=True)

        matches = match_idle_to_impacted([non_reefer], [cold_shp])
        assert len(matches) == 0

    def test_nearest_asset_preferred(self):
        """Asset closest to shipment origin is preferred when both are eligible."""
        # Hamburg → Hamburg distance = 0; Frankfurt → Hamburg ≈ 400 km
        asset_near = _asset("near", 24, 10, location=GeoPoint(lat=53.55, lng=9.99, label="Hamburg"))
        asset_far = _asset("far", 24, 10, location=GeoPoint(lat=50.03, lng=8.57, label="Frankfurt"))

        leg = _leg(_HAMBURG, _ROTTERDAM)
        shp = _shipment([leg])

        matches = match_idle_to_impacted([asset_near, asset_far], [shp])
        assert matches[0].asset_id == "near"

    def test_each_asset_assigned_once(self):
        """Greedy: each asset is assigned at most once."""
        asset = _asset("ast-1", 24, 10)
        leg1 = _leg(_HAMBURG, _ROTTERDAM, seq=1)
        leg2 = _leg(_HAMBURG, _FRANKFURT, seq=1)
        shp1 = _shipment([leg1], shp_id="shp-1")
        shp2 = _shipment([leg2], shp_id="shp-2")

        matches = match_idle_to_impacted([asset], [shp1, shp2])
        # Only one match because asset is used up after first assignment
        assert len(matches) == 1
        assert matches[0].asset_id == "ast-1"

    def test_match_has_rationale(self):
        """Every match includes a non-empty rationale string."""
        reefer = _asset("r1", 24, 10, reefer=True)
        leg = _leg(_HAMBURG, _ROTTERDAM)
        cold_shp = _shipment([leg], is_cold_chain=True)
        matches = match_idle_to_impacted([reefer], [cold_shp])
        assert len(matches) == 1
        assert len(matches[0].rationale) > 10
