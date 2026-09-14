"""
app/engines/impact.py — Disruption→shipment impact matching and scoring.

Deterministic. No network calls.

For circular affected areas: haversine distance from each leg's great-circle
path to the disruption centre. A leg is impacted if any INCOMPLETE leg's path
comes within the disruption radius during the disruption's active window.

For polygon areas: point-in-polygon test on sampled path points, plus node
matching on UN/LOCODE via affectedNodes.

A leg that has already COMPLETED is never impacted — getting this right is the
difference between a useful alert list and noise.

Impact score components:
  - delay_hours: estimated additional delay from rerouting or waiting
  - cargo_value_usd: direct financial exposure
  - cold_chain_exposure: delay pushes past remaining temperature-stable hours
  - cascade_legs: number of downstream legs still at risk
  - total_score: weighted composite (0–100)
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Sequence

from app.config import settings
from app.models.domain import (
    CircleArea,
    Decision,
    Disruption,
    GeoPoint,
    ImpactScore,
    Leg,
    LegStatus,
    PolygonArea,
    Severity,
    Shipment,
)

# ── Haversine ─────────────────────────────────────────────────────────────────

_EARTH_RADIUS_KM = 6_371.0


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two points in kilometres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def _interpolate_path(
    from_pt: GeoPoint,
    to_pt: GeoPoint,
    n_samples: int = 10,
) -> list[tuple[float, float]]:
    """
    Sample n_samples evenly spaced points along the great-circle path
    between two GeoPoints.  Returns (lat, lng) tuples.

    This is a linear interpolation in lat/lng space — sufficient for impact
    matching where exact path curvature matters less than whether the region
    is on or near the route.
    """
    points = []
    for i in range(n_samples + 1):
        t = i / n_samples
        lat = from_pt.lat + t * (to_pt.lat - from_pt.lat)
        lng = from_pt.lng + t * (to_pt.lng - from_pt.lng)
        points.append((lat, lng))
    return points


# ── Point-in-polygon (ray casting) ───────────────────────────────────────────

def _point_in_polygon(lat: float, lng: float, polygon: list[tuple[float, float]]) -> bool:
    """
    Ray casting algorithm for point-in-polygon test.
    Polygon vertices are (lat, lng) tuples in order.
    """
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > lng) != (yj > lng)) and (lat < (xj - xi) * (lng - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


# ── Leg intersection tests ─────────────────────────────────────────────────────

def _leg_intersects_circle(
    leg: Leg,
    center: GeoPoint,
    radius_km: float,
    disruption_start: datetime,
    disruption_end: datetime | None,
) -> bool:
    """
    True if this leg's path intersects the circle AND the leg's time window
    overlaps the disruption's active window.

    A completed leg is NEVER impacted.
    """
    if leg.status == LegStatus.completed:
        return False

    # Time window overlap: leg window [departs_at, arrives_at] must overlap
    # [disruption_start, disruption_end or +∞]
    leg_start = leg.departs_at
    leg_end = leg.arrives_at
    if disruption_end is not None and leg_start > disruption_end:
        return False   # Disruption resolved before leg starts
    if leg_end < disruption_start:
        return False   # Leg completes before disruption starts

    # Spatial: check all sampled path points
    path = _interpolate_path(leg.from_, leg.to)
    for lat, lng in path:
        d = haversine_km(lat, lng, center.lat, center.lng)
        if d <= radius_km:
            return True
    return False


def _leg_intersects_polygon(
    leg: Leg,
    polygon: list[tuple[float, float]],
    affected_nodes: list[str],
    disruption_start: datetime,
    disruption_end: datetime | None,
) -> bool:
    """
    True if this leg intersects the polygon area (path samples or node match)
    AND the time windows overlap.
    """
    if leg.status == LegStatus.completed:
        return False

    leg_start = leg.departs_at
    leg_end = leg.arrives_at
    if disruption_end is not None and leg_start > disruption_end:
        return False
    if leg_end < disruption_start:
        return False

    # Node matching by UN/LOCODE
    leg_nodes = set()
    if leg.from_.unlocode:
        leg_nodes.add(leg.from_.unlocode)
    if leg.to.unlocode:
        leg_nodes.add(leg.to.unlocode)
    if leg_nodes.intersection(affected_nodes):
        return True

    # Path sampling
    path = _interpolate_path(leg.from_, leg.to)
    for lat, lng in path:
        if _point_in_polygon(lat, lng, polygon):
            return True
    return False


def leg_is_impacted(
    leg: Leg,
    disruption: Disruption,
) -> bool:
    """
    True if this (incomplete) leg is impacted by the disruption.
    Completed legs are never impacted.
    """
    area = disruption.affected_area
    dis_start = disruption.started_at
    dis_end = disruption.expected_resolution_at

    if isinstance(area, CircleArea):
        return _leg_intersects_circle(leg, area.center, area.radius_km, dis_start, dis_end)
    elif isinstance(area, PolygonArea):
        return _leg_intersects_polygon(
            leg, area.polygon, disruption.affected_nodes, dis_start, dis_end
        )
    return False


# ── Impact scoring ─────────────────────────────────────────────────────────────

_DEFAULT_DELAY_HOURS_BY_SEVERITY = {
    Severity.critical: 96.0,
    Severity.major: 48.0,
    Severity.minor: 12.0,
    Severity.informational: 4.0,
}

# Assumed remaining temperature-stable hours for cold chain cargo if stranded
_COLD_CHAIN_STABLE_HOURS_DEFAULT = 72.0


def score_impact(
    shipment: Shipment,
    disruption: Disruption,
    impacted_legs: list[Leg],
    engine_version: str | None = None,
) -> ImpactScore:
    """
    Compute an impact score for a shipment against a disruption.

    Returns ImpactScore with full component breakdown and Decision.
    """
    if engine_version is None:
        engine_version = settings.engine_version

    now = datetime.now(timezone.utc)

    # Estimate delay: based on disruption severity
    delay_hours = _DEFAULT_DELAY_HOURS_BY_SEVERITY.get(disruption.severity, 24.0)

    cargo_value = shipment.cargo.value_usd

    # Cold chain exposure: does the delay push past remaining temperature-stable hours?
    cold_chain_exposure = False
    if shipment.cargo.is_cold_chain:
        eta = shipment.eta_projected
        # eta_projected may arrive as str (from JSON) or datetime
        if isinstance(eta, str):
            from datetime import datetime as _dt
            eta = _dt.fromisoformat(eta.replace("Z", "+00:00"))
        if eta > now:
            hours_to_delivery = (eta - now).total_seconds() / 3600.0
            # If delay would push beyond the stable window relative to remaining time
            if delay_hours > (_COLD_CHAIN_STABLE_HOURS_DEFAULT - hours_to_delivery):
                cold_chain_exposure = True

    # Cascade: downstream legs after the impacted ones
    impacted_ids = {leg.id for leg in impacted_legs}
    max_impacted_seq = max((leg.sequence for leg in impacted_legs), default=0)
    cascade_legs = sum(
        1 for leg in shipment.legs
        if leg.sequence > max_impacted_seq and leg.status != LegStatus.completed
    )

    # Scoring formula (components normalised to [0,1], then weighted)
    delay_score = min(delay_hours / 168.0, 1.0)         # cap at 1 week
    value_score = min(cargo_value / 1_000_000.0, 1.0)   # cap at $1M
    cc_score = 1.0 if cold_chain_exposure else 0.0
    cascade_score = min(cascade_legs / 5.0, 1.0)        # cap at 5 downstream legs

    # Weights: delay 35%, value 25%, cold chain 25%, cascade 15%
    total_score = (
        0.35 * delay_score
        + 0.25 * value_score
        + 0.25 * cc_score
        + 0.15 * cascade_score
    ) * 100.0

    rule_id = f"IMPACT-{disruption.severity.value.upper()}"
    citation = f"Disruption severity {disruption.severity.value}: estimated {delay_hours}h delay"

    decision = Decision(
        rule_pack_id="IMPACT_SCORING",
        rule_pack_version=engine_version,
        rule_id=rule_id,
        citation=citation,
        inputs={
            "disruption_id": disruption.id,
            "disruption_severity": disruption.severity.value,
            "disruption_confidence": disruption.confidence,
            "impacted_leg_count": len(impacted_legs),
            "estimated_delay_hours": delay_hours,
            "cargo_value_usd": cargo_value,
            "is_cold_chain": int(shipment.cargo.is_cold_chain),
            "cold_chain_exposure": int(cold_chain_exposure),
            "cascade_legs": cascade_legs,
        },
        evidence_record_ids=[leg.id for leg in impacted_legs],
        computed_at=now,
        engine_version=engine_version,
    )

    return ImpactScore(
        shipment_id=shipment.id,
        disruption_id=disruption.id,
        delay_hours=delay_hours,
        cargo_value_usd=cargo_value,
        cold_chain_exposure=cold_chain_exposure,
        cascade_legs=cascade_legs,
        total_score=round(total_score, 1),
        decision=decision,
    )


# ── Main entry point ──────────────────────────────────────────────────────────

def assess_disruption_impact(
    disruption: Disruption,
    shipments: list[Shipment],
    engine_version: str | None = None,
) -> list[ImpactScore]:
    """
    Assess which shipments are impacted by a disruption and score each.

    Returns a list of ImpactScore objects, sorted by total_score descending.
    Only shipments with at least one incomplete impacted leg are included.
    """
    results: list[ImpactScore] = []

    for shipment in shipments:
        impacted_legs = [
            leg for leg in shipment.legs
            if leg_is_impacted(leg, disruption)
        ]
        if not impacted_legs:
            continue
        score = score_impact(shipment, disruption, impacted_legs, engine_version)
        results.append(score)

    results.sort(key=lambda s: s.total_score, reverse=True)
    return results
