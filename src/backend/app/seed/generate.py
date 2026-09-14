"""
app/seed/generate.py — Deterministic world generator.

Given the scenario YAML and a random seed, produces:
  - NetworkNodeRow records
  - LaneRow records
  - ShipmentRow records (cohort + scripted)
  - FleetAssetRow records
  - RedeploymentMatchRow records
  - RerouteOptionRow records (stubbed; telemetry-driven ones added in Phase 3)

All randomness flows through a single seeded numpy.random.Generator object
passed to every function.  No global random state is mutated.

Usage (internal):
    from app.seed.generate import generate_world
    rows = generate_world(scenario, rng)
"""
from __future__ import annotations

import hashlib
import math
import pathlib
from datetime import datetime, timedelta, timezone
from typing import Any

import yaml

from app.models.orm import (
    FleetAssetRow,
    LaneRow,
    NetworkNodeRow,
    RedeploymentMatchRow,
    RerouteOptionRow,
    ShipmentRow,
)

_SCENARIO_DIR = pathlib.Path(__file__).parent / "scenarios"

# ── Synthetic name pools ──────────────────────────────────────────────────────
_SHIPPERS = [
    "Maersk Logistics", "Kuehne+Nagel", "DB Schenker", "DHL Supply Chain",
    "Panalpina Pharma", "UPS Healthcare", "Ceva Logistics", "Geodis",
    "XPO Logistics", "Sinotrans", "CEVA Cold Chain", "Hellmann Worldwide",
    "ALS Logistics", "Bolloré Logistics", "Yusen Logistics", "Kerry Logistics",
    "DSV Air & Sea", "Toll Holdings", "Nippon Express", "CJ Logistics",
]
_CONSIGNEES = [
    "MedSupply Europe GmbH", "Reckitt Distribution NL", "REWE Logistics DE",
    "NHS Supply Chain UK", "Sanofi Aventis DE", "Pfizer Distribution US",
    "Fresenius Kabi EU", "Bayer AG Warehouse", "Novartis Pharma EU",
    "Cardinal Health EU", "AstraZeneca Supply UK", "Merck KGaA Logistics",
    "Roche Distribution CH", "Abbott Cold Store NL", "Glenmark EU",
    "Stryker Medical EU", "Becton Dickinson DE", "Boston Scientific EU",
    "Medtronic Supply IE", "Johnson & Johnson DE",
]
_CARGO_DESCRIPTIONS = [
    "General merchandise — electronics", "Automotive spare parts",
    "Apparel and textiles", "Chemical intermediates", "Industrial machinery",
    "Consumer goods — FMCG", "Paper and packaging", "Rubber products",
    "Metal components", "Furniture and fixtures", "Plastics — raw resin",
    "Agricultural commodities — dried goods", "Construction materials",
    "Beverages — bottled", "Toys and sporting goods", "Office equipment",
    "Optical instruments", "Steel coils", "Tyres", "Home appliances",
]
_CARRIERS = {
    "ocean": ["Maersk", "MSC", "CMA CGM", "Hapag-Lloyd", "COSCO", "Evergreen", "MOL", "OOCL"],
    "road":  ["DB Schenker", "DHL Freight", "Kühne+Nagel", "DSV", "Raben Group", "Geodis"],
    "rail":  ["DB Cargo", "PKP Cargo", "Rail Cargo Austria", "CFL Cargo"],
    "air":   ["Lufthansa Cargo", "Emirates SkyCargo", "Singapore Airlines Cargo",
               "Air France KLM Cargo", "Cathay Pacific Cargo", "British Airways Cargo"],
}


def load_scenario(name: str = "storm_rotterdam") -> dict[str, Any]:
    """Load and return the raw scenario YAML as a dict."""
    path = _SCENARIO_DIR / f"{name}.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _anchor(scenario: dict) -> datetime:
    return datetime.fromisoformat(
        scenario["meta"]["scenario_anchor_utc"].replace("Z", "+00:00")
    )


# ── Network nodes ─────────────────────────────────────────────────────────────

def generate_nodes(scenario: dict) -> list[NetworkNodeRow]:
    rows = []
    for n in scenario["network_nodes"]:
        rows.append(NetworkNodeRow(
            code=n["code"],
            name=n["name"],
            node_type=n["node_type"],
            lat=n["lat"],
            lng=n["lng"],
            country=n["country"],
        ))
    return rows


def generate_lanes(scenario: dict) -> list[LaneRow]:
    rows = []
    for lane in scenario["lanes"]:
        rows.append(LaneRow(
            from_node=lane["from"],
            to_node=lane["to"],
            mode=lane["mode"],
            carrier=lane["carrier"],
            transit_hours=lane["transit_hours"],
            cost_per_unit=lane["cost_per_unit"],
            capacity=lane["capacity"],
            reefer_capable=bool(lane.get("reefer_capable", False)),
        ))
    return rows


# ── Node lookup helpers ───────────────────────────────────────────────────────

def _node_map(scenario: dict) -> dict[str, dict]:
    return {n["code"]: n for n in scenario["network_nodes"]}


def _geo(node: dict) -> dict:
    return {
        "lat": node["lat"],
        "lng": node["lng"],
        "label": node["name"],
        "unlocode": node["code"],
    }


# ── Shipment generation helpers ───────────────────────────────────────────────

def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _shipment_id(idx: int) -> str:
    return f"shp-{idx:03d}"


def _leg_id(shipment_id: str, seq: int) -> str:
    return f"leg-{shipment_id[4:]}-{seq}"


def _pick(rng, items: list):
    return items[rng.integers(len(items))]


def _status_from_distribution(rng, dist: dict[str, float]) -> str:
    """Sample a shipment status from a distribution dict."""
    r = rng.random()
    cumulative = 0.0
    for status, prob in dist.items():
        cumulative += prob
        if r < cumulative:
            return status
    return list(dist.keys())[-1]


def _make_leg(
    shipment_id: str,
    seq: int,
    mode: str,
    carrier: str,
    from_node: dict,
    to_node: dict,
    departs_at: datetime,
    transit_hours: float,
) -> dict:
    arrives_at = departs_at + timedelta(hours=transit_hours)
    leg_id = _leg_id(shipment_id, seq)
    now_plus_buffer = departs_at  # status logic handled by caller
    return {
        "id": leg_id,
        "sequence": seq,
        "mode": mode,
        "carrier": carrier,
        "from": _geo(from_node),
        "to": _geo(to_node),
        "departsAt": departs_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "arrivesAt": arrives_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "in_transit",
    }


def _make_shipment_row(
    shipment_id: str,
    reference: str,
    shipper: str,
    consignee: str,
    origin_node: dict,
    dest_node: dict,
    legs: list[dict],
    cargo: dict,
    eta_original: datetime,
    eta_projected: datetime,
    status: str,
    impacted_by: list[str],
    risk_score: float,
) -> ShipmentRow:
    data = {
        "id": shipment_id,
        "reference": reference,
        "shipper": shipper,
        "consignee": consignee,
        "origin": _geo(origin_node),
        "destination": _geo(dest_node),
        "legs": legs,
        "cargo": cargo,
        "etaOriginal": eta_original.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "etaProjected": eta_projected.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": status,
        "impactedBy": impacted_by,
        "riskScore": round(risk_score, 1),
    }
    return ShipmentRow(
        id=shipment_id,
        reference=reference,
        shipper=shipper,
        consignee=consignee,
        status=status,
        risk_score=risk_score,
        eta_original=eta_original,
        eta_projected=eta_projected,
        is_cold_chain=cargo.get("isColdChain", False),
        regulatory_regime=cargo.get("regulatoryRegime"),
        cargo_value_usd=cargo.get("valueUsd", 0),
        impacted_by=impacted_by,
        data=data,
    )


def _lane_lookup(scenario: dict) -> dict[tuple[str, str, str], dict]:
    """Return dict keyed by (from_node, to_node, mode)."""
    result: dict[tuple, dict] = {}
    for lane in scenario["lanes"]:
        key = (lane["from"], lane["to"], lane["mode"])
        result[key] = lane
    return result


def _find_lane(
    lane_map: dict,
    from_code: str,
    to_code: str,
    mode: str,
    rng,
    carriers: list[str] | None = None,
) -> dict | None:
    # Direct lane
    key = (from_code, to_code, mode)
    if key in lane_map:
        return lane_map[key]
    # Fallback: any lane from this node in this mode
    candidates = [v for k, v in lane_map.items() if k[0] == from_code and k[2] == mode]
    if candidates:
        return candidates[rng.integers(len(candidates))]
    return None


def _status_eta_slip(status: str, anchor: datetime, rng) -> tuple[datetime, datetime]:
    """Return (eta_original, eta_projected) given status."""
    base_hours = int(rng.integers(72, 600))
    eta_original = anchor + timedelta(hours=base_hours)
    if status == "on_track":
        slip = 0
    elif status == "at_risk":
        slip = int(rng.integers(4, 24))
    elif status == "delayed":
        slip = int(rng.integers(24, 96))
    else:  # exception
        slip = int(rng.integers(48, 168))
    eta_projected = eta_original + timedelta(hours=slip)
    return eta_original, eta_projected


def generate_cohort_shipments(
    scenario: dict,
    rng,
    start_id: int = 200,
) -> list[ShipmentRow]:
    """Generate cohort (non-scripted) shipments from cohort definitions."""
    anchor = _anchor(scenario)
    nodes = _node_map(scenario)
    lane_map = _lane_lookup(scenario)
    rows: list[ShipmentRow] = []
    idx = start_id

    for cohort in scenario["shipment_cohorts"]:
        for _ in range(cohort["count"]):
            shipment_id = _shipment_id(idx)
            idx += 1

            # Pick origin and destination
            origin_code = _pick(rng, cohort["origin_pool"])
            dest_pool = [c for c in cohort["destination_pool"] if c != origin_code]
            dest_code = _pick(rng, dest_pool) if dest_pool else cohort["destination_pool"][0]
            origin_node = nodes.get(origin_code)
            dest_node = nodes.get(dest_code)
            if not origin_node or not dest_node:
                continue

            # Mode
            modes = cohort["modes"]
            mode = _pick(rng, modes)
            carrier = _pick(rng, _CARRIERS.get(mode, ["Unknown Carrier"]))

            # Lane
            lane = _find_lane(lane_map, origin_code, dest_code, mode, rng)
            transit_hours = lane["transit_hours"] if lane else float(rng.integers(48, 500))

            # Status and ETA
            status = _status_from_distribution(rng, cohort["status_distribution"])
            eta_original, eta_projected = _status_eta_slip(status, anchor, rng)
            departs_at = eta_projected - timedelta(hours=transit_hours)

            # Legs
            legs = [
                _make_leg(
                    shipment_id, 1, mode, carrier,
                    origin_node, dest_node, departs_at, transit_hours,
                )
            ]

            # Cargo
            cargo_desc = _pick(rng, _CARGO_DESCRIPTIONS)
            cargo_value = float(rng.integers(10_000, 800_000))
            cargo = {
                "description": cargo_desc,
                "valueUsd": cargo_value,
                "isColdChain": False,
                "tempRangeC": None,
                "regulatoryRegime": None,
            }

            # Disruption exposure
            impacted_by: list[str] = []
            risk_score = 0.0
            for dis_id in cohort.get("disruption_exposure", []):
                if rng.random() < 0.35:  # ~35% chance of actual impact
                    impacted_by.append(dis_id)
                    risk_score = min(risk_score + rng.random() * 40, 100)

            # Risk score contribution from status
            status_risk = {"on_track": 0, "at_risk": 25, "delayed": 55, "exception": 80}
            risk_score = max(risk_score, status_risk.get(status, 0))
            risk_score = round(min(risk_score + rng.random() * 10, 100), 1)

            reference = f"SC-{2026}-{idx:05d}"
            rows.append(_make_shipment_row(
                shipment_id=shipment_id,
                reference=reference,
                shipper=_pick(rng, _SHIPPERS),
                consignee=_pick(rng, _CONSIGNEES),
                origin_node=origin_node,
                dest_node=dest_node,
                legs=legs,
                cargo=cargo,
                eta_original=eta_original,
                eta_projected=eta_projected,
                status=status,
                impacted_by=impacted_by,
                risk_score=risk_score,
            ))

    return rows


def generate_scripted_shipments(scenario: dict) -> list[ShipmentRow]:
    """
    Generate the six scripted cold-chain shipments from the scenario YAML.
    These have exact IDs, exact routes, and their leg structure is used by
    the telemetry generator.  Status is set to 'in_transit' or 'exception'
    based on the telemetry script.
    """
    anchor = _anchor(scenario)
    nodes = _node_map(scenario)
    lane_map = _lane_lookup(scenario)
    rows: list[ShipmentRow] = []

    # Status by telemetry script
    _script_status = {
        "clean_run": "on_track",
        "clean_run_minor_excursion": "at_risk",
        "critical_excursion_open": "exception",
        "freezing_excursion_resolved": "at_risk",
        "sensor_gap_and_stuck": "at_risk",
    }

    for s in scenario["scripted_shipments"]:
        shipment_id = s["id"]
        origin_code = s["origin"]
        dest_code = s["destination"]
        origin_node = nodes.get(origin_code)
        dest_node = nodes.get(dest_code)
        if not origin_node or not dest_node:
            raise ValueError(
                f"Scripted shipment {shipment_id}: node {origin_code!r} or {dest_code!r} not found"
            )

        modes = s["modes"]
        eta_original = anchor + timedelta(hours=s["eta_original_offset_h"])
        # ETA slip: exception = +48h, at_risk = +6h, on_track = 0
        status = _script_status.get(s["telemetry_script"], "on_track")
        slip_h = {"exception": 48, "at_risk": 6, "on_track": 0, "delayed": 24}.get(status, 0)
        eta_projected = eta_original + timedelta(hours=slip_h)

        # Build legs
        legs = []
        if len(modes) == 1:
            mode = modes[0]
            carrier = _CARRIERS.get(mode, ["Carrier"])[0]
            lane = lane_map.get((origin_code, dest_code, mode))
            transit_hours = lane["transit_hours"] if lane else s["eta_original_offset_h"] * 0.9
            departs_at = anchor - timedelta(hours=transit_hours * 0.5)
            legs.append(_make_leg(
                shipment_id, 1, mode, carrier,
                origin_node, dest_node, departs_at, transit_hours,
            ))
        else:
            # Multi-leg: use first mode for sea/air, second for road
            # Find a midpoint node from lanes
            mid_code = _find_midpoint(lane_map, origin_code, dest_code, modes, nodes)
            if mid_code and mid_code in nodes:
                mid_node = nodes[mid_code]
                mode1, mode2 = modes[0], modes[1]
                carrier1 = _CARRIERS.get(mode1, ["Carrier"])[0]
                carrier2 = _CARRIERS.get(mode2, ["Carrier"])[0]
                lane1 = lane_map.get((origin_code, mid_code, mode1))
                lane2 = lane_map.get((mid_code, dest_code, mode2))
                t1 = lane1["transit_hours"] if lane1 else s["eta_original_offset_h"] * 0.7
                t2 = lane2["transit_hours"] if lane2 else s["eta_original_offset_h"] * 0.3
                departs1 = anchor - timedelta(hours=t1 + t2)
                departs2 = departs1 + timedelta(hours=t1)
                legs.append(_make_leg(
                    shipment_id, 1, mode1, carrier1,
                    origin_node, mid_node, departs1, t1,
                ))
                legs.append(_make_leg(
                    shipment_id, 2, mode2, carrier2,
                    mid_node, dest_node, departs2, t2,
                ))
            else:
                # Fallback: single leg with first mode
                mode = modes[0]
                carrier = _CARRIERS.get(mode, ["Carrier"])[0]
                t = s["eta_original_offset_h"] * 0.9
                departs_at = anchor - timedelta(hours=t * 0.5)
                legs.append(_make_leg(
                    shipment_id, 1, mode, carrier,
                    origin_node, dest_node, departs_at, t,
                ))

        # Mark first leg as in_transit, others as scheduled
        if legs:
            legs[0]["status"] = "in_transit"
        for leg in legs[1:]:
            leg["status"] = "scheduled"

        # Cargo
        temp_range = s.get("temp_range_c")
        cargo = {
            "description": s["cargo_description"],
            "valueUsd": s["cargo_value_usd"],
            "isColdChain": True,
            "tempRangeC": temp_range,
            "regulatoryRegime": s["regulatory_regime"],
        }

        impacted_by = s.get("disruption_exposure", [])
        risk_map = {"exception": 85.0, "at_risk": 45.0, "on_track": 5.0, "delayed": 60.0}
        risk_score = risk_map.get(status, 20.0)

        rows.append(_make_shipment_row(
            shipment_id=shipment_id,
            reference=f"SC-CC-{shipment_id[4:].upper()}",
            shipper=s["shipper"],
            consignee=s["consignee"],
            origin_node=origin_node,
            dest_node=dest_node,
            legs=legs,
            cargo=cargo,
            eta_original=eta_original,
            eta_projected=eta_projected,
            status=status,
            impacted_by=impacted_by,
            risk_score=risk_score,
        ))

    return rows


def _find_midpoint(
    lane_map: dict,
    origin: str,
    dest: str,
    modes: list[str],
    nodes: dict,
) -> str | None:
    """
    Find a midpoint hub between origin and dest that has lanes on both modes.
    Used for multi-leg scripted shipments (e.g. ocean + road = port → inland hub).
    """
    mode1, mode2 = modes[0], modes[1]
    # Nodes reachable from origin on mode1
    from_origin = {k[1] for k in lane_map if k[0] == origin and k[2] == mode1}
    # Nodes that can reach dest on mode2
    to_dest = {k[0] for k in lane_map if k[1] == dest and k[2] == mode2}
    candidates = from_origin & to_dest
    # Prefer European ports for ocean → road
    preferred = ["NLRTM", "DEHAM", "BEFRA", "GBFXT"]
    for p in preferred:
        if p in candidates:
            return p
    return next(iter(candidates), None)


# ── Fleet generation ──────────────────────────────────────────────────────────

_ASSET_TYPES = {
    "truck": "truck",
    "trailer": "trailer",
    "container": "container",
    "reefer_container": "reefer_container",
    "vessel": "vessel",
}
_CAPACITY_BY_TYPE = {
    "truck": ("pallets", 33),
    "trailer": ("pallets", 33),
    "container": ("TEU", 1),
    "reefer_container": ("TEU", 1),
    "vessel": ("TEU", 14000),
}


def generate_fleet(scenario: dict, rng) -> list[FleetAssetRow]:
    """
    Generate fleet assets. First 2 are reefer containers near the critical
    demo shipment. Then idle assets with a realistic long-tail distribution.
    Then in-transit/maintenance assets.
    """
    anchor = _anchor(scenario)
    nodes = _node_map(scenario)
    fleet_cfg = scenario["fleet"]
    total = fleet_cfg["total_count"]
    idle_count = fleet_cfg["idle_count"]
    depot_pool = fleet_cfg["home_depot_pool"]

    # Build the idle-hours list from the distribution
    idle_hours_list: list[float] = []
    for bucket in fleet_cfg["idle_hours_distribution"]:
        lo, hi, count = bucket[0], bucket[1], bucket[2]
        for _ in range(count):
            idle_hours_list.append(float(rng.uniform(lo, hi)))
    # Sort descending so most-idle come first after the 2 guaranteed reefers
    idle_hours_list.sort(reverse=True)

    # Pad to idle_count - 2 (2 reserved for guaranteed reefers)
    while len(idle_hours_list) < idle_count - 2:
        idle_hours_list.append(float(rng.uniform(1, 24)))
    idle_hours_list = idle_hours_list[: idle_count - 2]

    # Build type list to match asset_type_distribution
    type_dist = fleet_cfg["asset_type_distribution"]
    type_list: list[str] = []
    for asset_type, count in type_dist.items():
        type_list.extend([asset_type] * count)
    rng.shuffle(type_list)

    rows: list[FleetAssetRow] = []
    asset_idx = 1

    # 2 guaranteed reefer containers near the critical shipment
    for i in range(2):
        asset_id = f"ast-{asset_idx:03d}"
        asset_idx += 1
        # Place near Rotterdam (shp-103 destination corridor)
        base_node = nodes.get("NLRTM", list(nodes.values())[0])
        lat = base_node["lat"] + float(rng.uniform(-0.5, 0.5))
        lng = base_node["lng"] + float(rng.uniform(-0.5, 0.5))
        idle_h = 48.0 + float(rng.uniform(0, 24))
        idle_since = anchor - timedelta(hours=idle_h)
        cap_unit, cap_val = _CAPACITY_BY_TYPE["reefer_container"]
        data = _fleet_data(
            asset_id, "reefer_container", "idle",
            lat, lng, "Rotterdam Yard",
            idle_since, idle_h, cap_unit, cap_val,
            utilisation_pct=float(rng.uniform(25, 55)),
            reefer_capable=True,
            home_depot="NLRTM",
        )
        rows.append(FleetAssetRow(
            id=asset_id,
            type="reefer_container",
            status="idle",
            reefer_capable=True,
            idle_since_hours=idle_h,
            capacity_value=cap_val,
            capacity_unit=cap_unit,
            home_depot="NLRTM",
            data=data,
        ))

    # Remaining idle assets
    for i, idle_h in enumerate(idle_hours_list):
        asset_id = f"ast-{asset_idx:03d}"
        asset_idx += 1
        asset_type = type_list[i % len(type_list)]
        depot_code = _pick(rng, depot_pool)
        depot_node = nodes.get(depot_code, list(nodes.values())[0])
        lat = depot_node["lat"] + float(rng.uniform(-1.0, 1.0))
        lng = depot_node["lng"] + float(rng.uniform(-1.0, 1.0))
        idle_since = anchor - timedelta(hours=idle_h)
        reefer = asset_type == "reefer_container"
        cap_unit, cap_val = _CAPACITY_BY_TYPE.get(asset_type, ("pallets", 33))
        data = _fleet_data(
            asset_id, asset_type, "idle",
            lat, lng, depot_node["name"],
            idle_since, idle_h, cap_unit, cap_val,
            utilisation_pct=float(rng.uniform(10, 70)),
            reefer_capable=reefer,
            home_depot=depot_code,
        )
        rows.append(FleetAssetRow(
            id=asset_id,
            type=asset_type,
            status="idle",
            reefer_capable=reefer,
            idle_since_hours=idle_h,
            capacity_value=cap_val,
            capacity_unit=cap_unit,
            home_depot=depot_code,
            data=data,
        ))

    # In-transit / maintenance assets for the remainder
    non_idle_types = ["truck", "trailer", "container", "reefer_container"]
    non_idle_statuses = ["in_transit", "in_transit", "in_transit", "maintenance", "reserved"]
    for _ in range(total - idle_count):
        asset_id = f"ast-{asset_idx:03d}"
        asset_idx += 1
        asset_type = _pick(rng, non_idle_types)
        status = _pick(rng, non_idle_statuses)
        depot_code = _pick(rng, depot_pool)
        depot_node = nodes.get(depot_code, list(nodes.values())[0])
        lat = depot_node["lat"] + float(rng.uniform(-2.0, 2.0))
        lng = depot_node["lng"] + float(rng.uniform(-2.0, 2.0))
        reefer = asset_type == "reefer_container"
        cap_unit, cap_val = _CAPACITY_BY_TYPE.get(asset_type, ("pallets", 33))
        # Non-idle assets: idleSinceAt is their last assignment time, idleSinceHours = 0
        data = _fleet_data(
            asset_id, asset_type, status,
            lat, lng, depot_node["name"],
            anchor - timedelta(hours=float(rng.uniform(1, 12))),
            0.0, cap_unit, cap_val,
            utilisation_pct=float(rng.uniform(55, 95)),
            reefer_capable=reefer,
            home_depot=depot_code,
        )
        rows.append(FleetAssetRow(
            id=asset_id,
            type=asset_type,
            status=status,
            reefer_capable=reefer,
            idle_since_hours=0.0,
            capacity_value=cap_val,
            capacity_unit=cap_unit,
            home_depot=depot_code,
            data=data,
        ))

    return rows


def _fleet_data(
    asset_id: str,
    asset_type: str,
    status: str,
    lat: float,
    lng: float,
    location_label: str,
    idle_since: datetime,
    idle_hours: float,
    cap_unit: str,
    cap_val: float,
    utilisation_pct: float,
    reefer_capable: bool,
    home_depot: str,
) -> dict:
    return {
        "id": asset_id,
        "type": asset_type,
        "status": status,
        "location": {
            "lat": round(lat, 4),
            "lng": round(lng, 4),
            "label": location_label,
        },
        "idleSinceAt": idle_since.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "idleSinceHours": round(idle_hours, 1),
        "capacity": {"unit": cap_unit, "value": cap_val},
        "utilisationPct30d": round(utilisation_pct, 1),
        "reeferCapable": reefer_capable,
        "homeDepot": home_depot,
    }


# ── Redeployment matches ──────────────────────────────────────────────────────

def generate_redeployment_matches(
    fleet_rows: list[FleetAssetRow],
    scripted_shipment_rows: list[ShipmentRow],
    anchor: datetime,
) -> list[RedeploymentMatchRow]:
    """
    Generate redeployment matches: pair idle reefer assets with scripted
    cold-chain shipments that need help.
    """
    idle_reefers = [f for f in fleet_rows if f.status == "idle" and f.reefer_capable]
    # Scripted cold-chain shipments that are not on_track
    candidate_shipments = [
        s for s in scripted_shipment_rows if s.status in ("exception", "at_risk")
    ]

    rows: list[RedeploymentMatchRow] = []
    used_assets: set[str] = set()

    for ship in candidate_shipments:
        # Find closest idle reefer
        ship_data = ship.data
        origin = ship_data.get("origin", {})
        ship_lat = origin.get("lat", 0)
        ship_lng = origin.get("lng", 0)

        best_asset = None
        best_dist = float("inf")
        for asset in idle_reefers:
            if asset.id in used_assets:
                continue
            a_data = asset.data
            a_loc = a_data.get("location", {})
            dist = _haversine_km(
                a_loc.get("lat", 0), a_loc.get("lng", 0),
                ship_lat, ship_lng,
            )
            if dist < best_dist:
                best_dist = dist
                best_asset = asset

        if best_asset is None:
            continue
        used_assets.add(best_asset.id)

        hours = best_dist / 60.0  # 60 km/h positioning speed
        a_data = best_asset.data
        a_loc = a_data.get("location", {})
        util_gain = round(max(0, (1.0 - a_data.get("utilisationPct30d", 50) / 100.0) * 40.0), 1)

        rows.append(RedeploymentMatchRow(
            asset_id=best_asset.id,
            shipment_id=ship.id,
            distance_km=round(best_dist, 1),
            hours_to_position=round(hours, 1),
            utilisation_gain_pct=util_gain,
            rationale=(
                f"{a_data.get('type', 'asset').replace('_', ' ').title()} idle at "
                f"{a_loc.get('label', 'unknown')} — "
                f"{best_dist:.0f}km from {origin.get('label', 'origin')}, "
                f"~{hours:.1f}h to position. Reefer capable."
            ),
            generated_at=anchor,
        ))

    return rows


# ── Reroute options ───────────────────────────────────────────────────────────

def generate_reroute_options(
    scripted_shipment_rows: list[ShipmentRow],
    scenario: dict,
) -> list[RerouteOptionRow]:
    """
    Generate stub reroute options for impacted scripted shipments.
    Two options per impacted shipment: fast (air upgrade) + slow (detour).
    The full rerouting engine can regenerate these, but these pre-seeded
    versions ensure the frontend always has data to display.
    """
    nodes = _node_map(scenario)
    rows: list[RerouteOptionRow] = []

    def _reroute_id(ship_id: str, variant: str) -> str:
        return f"rrt-{ship_id[4:]}-{variant}"

    for ship in scripted_shipment_rows:
        if ship.status not in ("exception", "at_risk"):
            continue

        ship_data = ship.data
        legs = ship_data.get("legs", [])
        if not legs:
            continue
        first_leg = legs[0]
        last_leg = legs[-1]

        # Option A: recommended — maintain cold chain, slight delay
        opt_a_id = _reroute_id(ship.id, "a")
        new_legs_a = [
            {
                **first_leg,
                "id": f"{first_leg['id']}-alt",
                "carrier": "Alternate Carrier",
                "status": "scheduled",
            }
        ]
        opt_a_data = {
            "id": opt_a_id,
            "shipmentId": ship.id,
            "summary": "Reroute via Hamburg — avoids disruption zone, reefer maintained",
            "replacesLegIds": [first_leg["id"]],
            "newLegs": new_legs_a,
            "deltaDays": 1.5,
            "deltaCostUsd": 4200,
            "co2DeltaKg": 120,
            "coldChainContinuity": "maintained",
            "coldChainContinuityReason": "Reefer service available on alternate lane",
            "feasibility": "confirmed",
            "constraints": ["Booking must be confirmed within 4h"],
            "rationale": (
                "Rerouting through Hamburg avoids the disruption corridor. "
                "Reefer service is confirmed available. 1.5-day delay versus "
                "48-72h blockage on current route."
            ),
            "recommended": True,
        }
        rows.append(RerouteOptionRow(
            id=opt_a_id,
            shipment_id=ship.id,
            feasibility="confirmed",
            cold_chain_continuity="maintained",
            recommended=True,
            delta_days=1.5,
            delta_cost_usd=4200,
            data=opt_a_data,
        ))

        # Option B: faster but cold chain at risk
        opt_b_id = _reroute_id(ship.id, "b")
        new_legs_b = [
            {
                **first_leg,
                "id": f"{first_leg['id']}-air",
                "mode": "air",
                "carrier": "Air Freight Express",
                "status": "scheduled",
            }
        ]
        opt_b_data = {
            "id": opt_b_id,
            "shipmentId": ship.id,
            "summary": "Upgrade to air freight — fastest option, higher cost",
            "replacesLegIds": [first_leg["id"]],
            "newLegs": new_legs_b,
            "deltaDays": -1.0,
            "deltaCostUsd": 18500,
            "co2DeltaKg": 850,
            "coldChainContinuity": "at_risk",
            "coldChainContinuityReason": (
                "Air transfer requires 2h ground handling at departure airport "
                "without guaranteed reefer."
            ),
            "feasibility": "likely",
            "constraints": [
                "Air slot available but not confirmed",
                "Ground handling time creates cold chain gap risk",
            ],
            "rationale": (
                "Air upgrade recovers 1 day but adds significant cost and CO2. "
                "Ground handling creates a 2h cold chain gap risk at origin airport."
            ),
            "recommended": False,
        }
        rows.append(RerouteOptionRow(
            id=opt_b_id,
            shipment_id=ship.id,
            feasibility="likely",
            cold_chain_continuity="at_risk",
            recommended=False,
            delta_days=-1.0,
            delta_cost_usd=18500,
            data=opt_b_data,
        ))

    return rows


# ── Main entry point ──────────────────────────────────────────────────────────

def generate_world(scenario: dict, rng) -> dict[str, list]:
    """
    Generate the complete seeded world.

    Returns a dict with keys: nodes, lanes, shipments, fleet,
    redeployment_matches, reroute_options.
    """
    anchor = _anchor(scenario)

    nodes = generate_nodes(scenario)
    lanes = generate_lanes(scenario)
    scripted = generate_scripted_shipments(scenario)
    cohort = generate_cohort_shipments(scenario, rng, start_id=200)
    all_shipments = scripted + cohort
    fleet = generate_fleet(scenario, rng)
    redeploy = generate_redeployment_matches(fleet, scripted, anchor)
    reroutes = generate_reroute_options(scripted, scenario)

    return {
        "nodes": nodes,
        "lanes": lanes,
        "shipments": all_shipments,
        "fleet": fleet,
        "redeployment_matches": redeploy,
        "reroute_options": reroutes,
    }
