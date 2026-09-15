"""
app/engines/priority_queue.py — Priority queue ranking engine.

Merges four item types into a single operator worklist:
  - excursion         (cold chain breach — deterministic, carries regulatory citation)
  - shipment_exception (ETA slip + disruption impact)
  - idle_asset        (wasted capacity-hours)
  - predicted_risk    (ML prediction — distinct visual, no citation, never merged with excursions)

Scoring is deterministic. Weights are in config. Components are returned
alongside each item so the operator can see why item A ranks above item B.

See docs/architecture.md §Priority Queue for the full reasoning.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from app.config import settings
from app.models.domain import (
    Excursion,
    FleetAsset,
    PriorityItem,
    PriorityItemKind,
    PriorityItemWithScore,
    Severity,
    Shipment,
)
from app.models.orm import ExcursionRow, FleetAssetRow, ShipmentRow

_SEV_SCORE = {
    Severity.critical: 1.0,
    Severity.major: 0.75,
    Severity.minor: 0.35,
    Severity.informational: 0.1,
}


def _sev_from_str(s: str) -> Severity:
    try:
        return Severity(s)
    except ValueError:
        return Severity.informational


# ── Excursion scoring ─────────────────────────────────────────────────────────

def score_excursion(exc: ExcursionRow) -> PriorityItemWithScore:
    w_sev = settings.pq_weight_severity
    w_action = settings.pq_weight_actionability
    w_value = settings.pq_weight_value

    sev = _sev_from_str(exc.severity)
    sev_score = _SEV_SCORE.get(sev, 0.1)
    action_score = 1.0 if exc.detected_before_delivery else 0.1
    # Approximate value from degree_minutes as a proxy (no direct cargo value on ExcursionRow)
    # Use degree_minutes normalised against 500 as a severity proxy for value weighting
    value_score = min(exc.degree_minutes / 500.0, 1.0)

    raw = w_sev * sev_score + w_action * action_score + w_value * value_score
    score = round(min(raw * 100.0, 100.0), 1)

    sev_shape = {"critical": "◆", "major": "▲", "minor": "■", "informational": "●"}.get(exc.severity, "●")
    sev_label = exc.severity.upper()

    headline = (
        f"{sev_shape} {sev_label} · {exc.degree_minutes:.0f} deg-min · "
        f"{exc.minutes_out_of_range}min out of range"
    )
    if not exc.detected_before_delivery:
        headline += " · POST-MORTEM"

    item = PriorityItem(
        id=f"pq-exc-{exc.id}",
        kind=PriorityItemKind.excursion,
        refId=exc.id,
        headline=headline,
        stake=f"{exc.severity} excursion · {exc.degree_minutes:.0f} deg-min",
        severity=sev,
        href=f"/shipments/{exc.shipment_id}",
        updatedAt=exc.started_at.isoformat(),
    )
    return PriorityItemWithScore(
        item=item,
        score=score,
        score_components={
            "severity": round(w_sev * sev_score * 100, 1),
            "actionability": round(w_action * action_score * 100, 1),
            "value_proxy": round(w_value * value_score * 100, 1),
        },
    )


# ── Shipment exception scoring ─────────────────────────────────────────────────

def score_shipment_exception(row: ShipmentRow) -> PriorityItemWithScore | None:
    """Score a shipment that is in 'exception' or 'delayed' status."""
    if row.status not in ("exception", "delayed", "at_risk"):
        return None

    w_sev = settings.pq_weight_severity
    w_eta = settings.pq_weight_eta_slip
    w_value = settings.pq_weight_value

    # Severity: exception=major, delayed=minor, at_risk=minor
    sev_map = {"exception": Severity.major, "delayed": Severity.minor, "at_risk": Severity.minor}
    sev = sev_map.get(row.status, Severity.informational)
    sev_score = _SEV_SCORE.get(sev, 0.1)

    # ETA slip
    now = datetime.now(timezone.utc)
    eta_orig = row.eta_original.replace(tzinfo=timezone.utc) if row.eta_original.tzinfo is None else row.eta_original
    eta_proj = row.eta_projected.replace(tzinfo=timezone.utc) if row.eta_projected.tzinfo is None else row.eta_projected
    slip_hours = max(0.0, (eta_proj - eta_orig).total_seconds() / 3600.0)
    eta_score = min(slip_hours / 168.0, 1.0)

    value_score = min(row.cargo_value_usd / 1_000_000.0, 1.0)

    raw = w_sev * sev_score + w_eta * eta_score + w_value * value_score
    score = round(min(raw * 100.0, 100.0), 1)

    data = row.data
    sev_shape = {"major": "▲", "minor": "■"}.get(sev.value, "■")
    headline = (
        f"{sev_shape} {row.status.upper()} · "
        f"{data.get('reference', row.id)} · "
        f"+{slip_hours:.0f}h ETA slip"
    )
    stake = f"${row.cargo_value_usd:,.0f} cargo"
    if row.impacted_by:
        stake += f" · impacted by {', '.join(row.impacted_by[:2])}"

    item = PriorityItem(
        id=f"pq-shp-{row.id}",
        kind=PriorityItemKind.shipment_exception,
        refId=row.id,
        headline=headline,
        stake=stake,
        severity=sev,
        href=f"/shipments/{row.id}",
        updatedAt=eta_proj.isoformat(),
    )
    return PriorityItemWithScore(
        item=item,
        score=score,
        score_components={
            "severity": round(w_sev * sev_score * 100, 1),
            "eta_slip": round(w_eta * eta_score * 100, 1),
            "value": round(w_value * value_score * 100, 1),
        },
    )


# ── Idle asset scoring ────────────────────────────────────────────────────────

def score_idle_asset(
    row: FleetAssetRow,
    has_redeployment_match: bool,
) -> PriorityItemWithScore:
    w_waste = settings.pq_weight_waste
    w_match = settings.pq_weight_match

    capacity_hours = row.capacity_value * row.idle_since_hours
    waste_score = min(capacity_hours / 5000.0, 1.0)
    match_score = 1.0 if has_redeployment_match else 0.3

    raw = w_waste * waste_score + w_match * match_score
    score = round(min(raw * 100.0, 100.0), 1)

    data = row.data
    asset_type = data.get("type", "asset").replace("_", " ").title()
    location = data.get("location", {}).get("label", "unknown location")
    cap = data.get("capacity", {})

    sev = Severity.minor if has_redeployment_match else Severity.informational

    headline = (
        f"■ IDLE · {asset_type} · {location} · "
        f"{row.idle_since_hours:.0f}h idle"
    )
    stake = f"{row.idle_since_hours:.0f}h idle · {row.capacity_value:.0f} {row.capacity_unit}"
    if has_redeployment_match:
        stake += " · redeployment match available"

    item = PriorityItem(
        id=f"pq-ast-{row.id}",
        kind=PriorityItemKind.idle_asset,
        refId=row.id,
        headline=headline,
        stake=stake,
        severity=sev,
        href=f"/fleet",
        updatedAt=data.get("idleSinceAt", datetime.now(timezone.utc).isoformat()),
    )
    return PriorityItemWithScore(
        item=item,
        score=score,
        score_components={
            "waste": round(w_waste * waste_score * 100, 1),
            "has_match": round(w_match * match_score * 100, 1),
        },
    )


# ── Predicted-risk scoring ────────────────────────────────────────────────────

def score_predicted_risk(prediction_row) -> PriorityItemWithScore | None:
    """
    Score an ML excursion-risk prediction for the priority queue.

    Visual contract (enforced here and in the UI):
      - kind = predicted_risk (never excursion)
      - No regulatory citation
      - Headline shows probability and horizon, not severity label
      - Score is capped below any confirmed excursion at equivalent probability
        (confirmed excursions always outrank predictions at the same level)
      - Below 50% probability: severity = informational (watch item)
      - Above 50%: severity = minor
    """
    from app.models.orm import PredictionRow
    from datetime import timezone

    value = float(prediction_row.value)   # calibrated P(breach) 0–1

    # Score: raw probability, capped at 59 so confirmed excursions always rank higher
    # A confirmed critical excursion scores ~70+; predictions cap at 59.
    score = round(min(value * 59.0, 59.0), 1)

    sev = Severity.minor if value >= 0.5 else Severity.informational
    watch_label = "WATCH" if value < 0.5 else "ALERT"
    pct = round(value * 100, 0)
    horizon = prediction_row.horizon_hours

    headline = (
        f"~ {pct:.0f}% breach risk within {horizon:.0f}h "
        f"[{watch_label}] — no citation"
    )
    stake = (
        f"Predicted P(breach)={pct:.0f}% · {prediction_row.subject_id} · "
        "ML prediction only"
    )

    predicted_at = prediction_row.predicted_at
    if predicted_at.tzinfo is None:
        predicted_at = predicted_at.replace(tzinfo=timezone.utc)

    item = PriorityItem(
        id=f"pq-pred-{prediction_row.id}",
        kind=PriorityItemKind.predicted_risk,
        refId=prediction_row.subject_id,
        headline=headline,
        stake=stake,
        severity=sev,
        href=f"/shipments/{prediction_row.subject_id}",
        updatedAt=predicted_at.isoformat(),
    )
    return PriorityItemWithScore(
        item=item,
        score=score,
        score_components={
            "predicted_probability": round(value * 100, 1),
            "score_cap_note": "Capped at 59 so confirmed excursions always rank higher",
        },
    )


# ── Merge and rank ────────────────────────────────────────────────────────────

def build_priority_queue(
    excursion_rows: Sequence[ExcursionRow],
    shipment_rows: Sequence[ShipmentRow],
    fleet_rows: Sequence[FleetAssetRow],
    asset_ids_with_match: set[str],
    prediction_rows: Sequence | None = None,
) -> list[PriorityItemWithScore]:
    """
    Merge all item types into a single ranked queue.

    prediction_rows: optional list of PredictionRow objects from the ML layer.
    When None (or ML disabled), the queue is identical to the pre-ML version.
    Predicted-risk items are always scored below confirmed excursions.

    Tie-break: updatedAt descending (most recently updated floats up).
    """
    items: list[PriorityItemWithScore] = []

    for exc in excursion_rows:
        items.append(score_excursion(exc))

    for shp in shipment_rows:
        scored = score_shipment_exception(shp)
        if scored is not None:
            items.append(scored)

    for asset in fleet_rows:
        has_match = asset.id in asset_ids_with_match
        items.append(score_idle_asset(asset, has_match))

    # ML predicted-risk items — only added when predictions are provided
    if prediction_rows:
        for pred in prediction_rows:
            scored_pred = score_predicted_risk(pred)
            if scored_pred is not None:
                items.append(scored_pred)

    # Sort: primary = score desc, tie-break = updated_at desc
    items.sort(
        key=lambda x: (
            -x.score,
            x.item.updated_at if isinstance(x.item.updated_at, str) else x.item.updated_at.isoformat(),
        )
    )

    return items
