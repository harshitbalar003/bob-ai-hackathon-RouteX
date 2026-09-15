"""
app/models/domain.py — Pydantic v2 domain models.

FIELD CONTRACT: Every public model here must stay field-for-field identical to
src/frontend/src/types/domain.ts.  If you change a field name, type, or
nullability here, update domain.ts in the same commit (and vice-versa).

Backend-only models (RulePack, SeverityRule, Decision, TempRange) are marked
with "# backend-only" and have no TypeScript counterpart.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator


# ─── Primitives ──────────────────────────────────────────────────────────────

class Mode(str, Enum):
    ocean = "ocean"
    air = "air"
    road = "road"
    rail = "rail"


class Severity(str, Enum):
    informational = "informational"
    minor = "minor"
    major = "major"
    critical = "critical"


class DisruptionType(str, Enum):
    weather = "weather"
    labour_action = "labour_action"
    geopolitical = "geopolitical"
    congestion = "congestion"
    infrastructure = "infrastructure"
    customs = "customs"


class GeoPoint(BaseModel):
    lat: float
    lng: float
    label: str
    unlocode: Optional[str] = None


# ─── Shipment & Leg ──────────────────────────────────────────────────────────

class LegStatus(str, Enum):
    completed = "completed"
    in_transit = "in_transit"
    scheduled = "scheduled"
    blocked = "blocked"


class Leg(BaseModel):
    id: str
    sequence: int
    mode: Mode
    carrier: str
    from_: GeoPoint = Field(alias="from")
    to: GeoPoint
    departs_at: datetime = Field(alias="departsAt")
    arrives_at: datetime = Field(alias="arrivesAt")
    status: LegStatus

    model_config = {"populate_by_name": True}


class RegulatoryRegime(str, Enum):
    """Regulatory regime for cold-chain cargo. Field is optional; absence = no regime."""
    GDP = "GDP"
    WHO_PQS = "WHO_PQS"
    USP_1079 = "USP_1079"
    FSMA = "FSMA"


class Cargo(BaseModel):
    description: str
    value_usd: float = Field(alias="valueUsd")
    is_cold_chain: bool = Field(alias="isColdChain")
    temp_range_c: Optional[dict[Literal["min", "max"], float]] = Field(
        default=None, alias="tempRangeC"
    )
    regulatory_regime: Optional[RegulatoryRegime] = Field(
        default=None, alias="regulatoryRegime"
    )

    model_config = {"populate_by_name": True}


class ShipmentStatus(str, Enum):
    on_track = "on_track"
    at_risk = "at_risk"
    delayed = "delayed"
    exception = "exception"


class Shipment(BaseModel):
    id: str
    reference: str
    shipper: str
    consignee: str
    origin: GeoPoint
    destination: GeoPoint
    legs: list[Leg]
    cargo: Cargo
    eta_original: datetime = Field(alias="etaOriginal")
    eta_projected: datetime = Field(alias="etaProjected")
    status: ShipmentStatus
    impacted_by: list[str] = Field(alias="impactedBy")
    risk_score: float = Field(alias="riskScore")

    model_config = {"populate_by_name": True}


# ─── Disruption ──────────────────────────────────────────────────────────────

class CircleArea(BaseModel):
    center: GeoPoint
    radius_km: float = Field(alias="radiusKm")

    model_config = {"populate_by_name": True}


class PolygonArea(BaseModel):
    polygon: list[tuple[float, float]]


DisruptionArea = Annotated[
    Union[CircleArea, PolygonArea],
    Field(discriminator=None),  # no literal discriminator; use Union directly
]


class Disruption(BaseModel):
    id: str
    type: DisruptionType
    headline: str
    detail: str
    severity: Severity
    started_at: datetime = Field(alias="startedAt")
    expected_resolution_at: Optional[datetime] = Field(
        default=None, alias="expectedResolutionAt"
    )
    confidence: float  # 0–1
    source: str
    affected_area: Union[CircleArea, PolygonArea] = Field(alias="affectedArea")
    affected_nodes: list[str] = Field(alias="affectedNodes")

    model_config = {"populate_by_name": True}

    @field_validator("confidence")
    @classmethod
    def confidence_range(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        return v


# ─── Reroute ─────────────────────────────────────────────────────────────────

class ColdChainContinuity(str, Enum):
    maintained = "maintained"
    at_risk = "at_risk"
    broken = "broken"


class RerouteFeasibility(str, Enum):
    confirmed = "confirmed"
    likely = "likely"
    speculative = "speculative"


class RerouteOption(BaseModel):
    id: str
    shipment_id: str = Field(alias="shipmentId")
    summary: str
    replaces_leg_ids: list[str] = Field(alias="replacesLegIds")
    new_legs: list[Leg] = Field(alias="newLegs")
    delta_days: float = Field(alias="deltaDays")
    delta_cost_usd: float = Field(alias="deltaCostUsd")
    co2_delta_kg: float = Field(alias="co2DeltaKg")
    cold_chain_continuity: ColdChainContinuity = Field(alias="coldChainContinuity")
    cold_chain_continuity_reason: Optional[str] = Field(
        default=None, alias="coldChainContinuityReason"
    )
    feasibility: RerouteFeasibility
    constraints: list[str]
    rationale: str
    recommended: bool

    model_config = {"populate_by_name": True}


# ─── Fleet ───────────────────────────────────────────────────────────────────

class AssetType(str, Enum):
    truck = "truck"
    trailer = "trailer"
    container = "container"
    reefer_container = "reefer_container"
    vessel = "vessel"


class AssetStatus(str, Enum):
    idle = "idle"
    in_transit = "in_transit"
    maintenance = "maintenance"
    reserved = "reserved"


class AssetCapacity(BaseModel):
    unit: Literal["TEU", "pallets", "kg"]
    value: float


class FleetAsset(BaseModel):
    id: str
    type: AssetType
    status: AssetStatus
    location: GeoPoint
    idle_since_at: datetime = Field(alias="idleSinceAt")
    idle_since_hours: float = Field(alias="idleSinceHours")
    capacity: AssetCapacity
    utilisation_pct_30d: float = Field(alias="utilisationPct30d")
    reefer_capable: bool = Field(alias="reeferCapable")
    home_depot: str = Field(alias="homeDepot")

    model_config = {"populate_by_name": True}


class RedeploymentMatch(BaseModel):
    asset_id: str = Field(alias="assetId")
    shipment_id: str = Field(alias="shipmentId")
    distance_km: float = Field(alias="distanceKm")
    hours_to_position: float = Field(alias="hoursToPosition")
    utilisation_gain_pct: float = Field(alias="utilisationGainPct")
    rationale: str
    generated_at: datetime = Field(alias="generatedAt")

    model_config = {"populate_by_name": True}


# ─── Cold Chain / Sensors ────────────────────────────────────────────────────

class SensorReading(BaseModel):
    shipment_id: str = Field(alias="shipmentId")
    sensor_id: str = Field(alias="sensorId")
    leg_id: str = Field(alias="legId")
    timestamp: datetime
    temp_c: float = Field(alias="tempC")
    humidity_pct: Optional[float] = Field(default=None, alias="humidityPct")
    door_open: Optional[bool] = Field(default=None, alias="doorOpen")

    model_config = {"populate_by_name": True}

    @property
    def reading_id(self) -> str:
        """Stable canonical ID: {shipmentId}:{sensorId}:{timestamp_ms}"""
        ts_ms = int(self.timestamp.timestamp() * 1000)
        return f"{self.shipment_id}:{self.sensor_id}:{ts_ms}"


class SensorGap(BaseModel):
    shipment_id: str = Field(alias="shipmentId")
    sensor_id: str = Field(alias="sensorId")
    leg_id: str = Field(alias="legId")
    gap_start_at: datetime = Field(alias="gapStartAt")
    gap_end_at: datetime = Field(alias="gapEndAt")
    duration_minutes: int = Field(alias="durationMinutes")

    model_config = {"populate_by_name": True}


class ExcursionDisposition(str, Enum):
    release = "release"
    quarantine_pending_QA = "quarantine_pending_QA"
    reject = "reject"


class Excursion(BaseModel):
    id: str
    shipment_id: str = Field(alias="shipmentId")
    leg_id: str = Field(alias="legId")
    started_at: datetime = Field(alias="startedAt")
    ended_at: Optional[datetime] = Field(default=None, alias="endedAt")
    peak_temp_c: float = Field(alias="peakTempC")
    minutes_out_of_range: int = Field(alias="minutesOutOfRange")
    degree_minutes: float = Field(alias="degreeMinutes")
    mean_kinetic_temp_c: float = Field(alias="meanKineticTempC")
    severity: Severity
    regulatory_basis: str = Field(alias="regulatoryBasis")
    disposition: ExcursionDisposition
    evidence_reading_ids: list[str] = Field(alias="evidenceReadingIds")
    detected_before_delivery: bool = Field(alias="detectedBeforeDelivery")

    model_config = {"populate_by_name": True}


# ─── Priority Queue ───────────────────────────────────────────────────────────

class PriorityItemKind(str, Enum):
    shipment_exception = "shipment_exception"
    excursion = "excursion"
    idle_asset = "idle_asset"
    predicted_risk = "predicted_risk"   # ML prediction — dashed visual, no citation


class PriorityItem(BaseModel):
    id: str
    kind: PriorityItemKind
    ref_id: str = Field(alias="refId")
    headline: str
    stake: str
    severity: Severity
    href: str
    updated_at: datetime = Field(alias="updatedAt")

    model_config = {"populate_by_name": True}


# ─── Backend-only models ─────────────────────────────────────────────────────
# These are not mirrored in domain.ts.

class TempRange(BaseModel):  # backend-only
    min: float
    max: float


class SeverityRule(BaseModel):  # backend-only
    """A single rule in a rule pack. First match wins."""
    id: str
    severity: Severity
    citation: str
    min_degree_minutes: Optional[float] = None
    min_minutes_out_of_range: Optional[int] = None
    max_temp_exceeded_by_c: Optional[float] = None
    below_range: Optional[bool] = None  # True = freezing; more severe for vaccine cargo
    applies_to_cargo: Optional[list[str]] = None  # None = all cargo types


class RulePack(BaseModel):  # backend-only
    """
    Loaded from YAML at startup. One file per regulatory regime.
    Changing a severity threshold = edit the YAML + bump version. No Python change.
    """
    id: str                        # "GDP" | "WHO_PQS" | "USP_1079" | "FSMA"
    version: str
    display_name: str
    citation_base: str
    allowed_range_c: TempRange
    severity_rules: list[SeverityRule]   # evaluated in order, first match wins
    disposition_map: dict[str, str]      # Severity value → ExcursionDisposition value


class Decision(BaseModel):  # backend-only
    """
    Attached to every classification, score, and ranking returned by an engine.
    Every verdict-bearing response carries one of these — the system is fully
    auditable without a language model.
    """
    rule_pack_id: str
    rule_pack_version: str
    rule_id: str
    citation: str
    inputs: dict[str, float | int | str]   # actual values that fired the rule
    evidence_record_ids: list[str]
    computed_at: datetime
    engine_version: str


class DataGap(BaseModel):  # backend-only
    """
    A gap in sensor coverage detected during cold-chain analysis.
    A gap over a cold-chain leg is itself a compliance finding.
    """
    shipment_id: str
    sensor_id: str
    leg_id: str
    gap_start_at: datetime
    gap_end_at: datetime
    duration_minutes: float
    is_compliance_finding: bool   # True if leg is cold-chain and gap > threshold


class ExcursionWithDecision(BaseModel):  # backend-only
    """Excursion enriched with its audit Decision — returned by the engine."""
    excursion: Excursion
    decision: Decision
    data_gaps: list[DataGap] = []
    door_open_correlated: bool = False
    sensor_suspect: bool = False        # True if stuck-value flag was active


class ImpactScore(BaseModel):  # backend-only
    """Score components for a disruption→shipment impact, returned separately."""
    shipment_id: str
    disruption_id: str
    delay_hours: float
    cargo_value_usd: float
    cold_chain_exposure: bool   # delay pushes past remaining stable hours
    cascade_legs: int           # downstream legs still at risk
    total_score: float          # 0–100, weighted composite
    decision: Decision


class PriorityItemWithScore(BaseModel):  # backend-only
    """Priority item enriched with its numeric score for the operator queue."""
    item: PriorityItem
    score: float          # 0–100
    score_components: dict[str, float]   # component breakdown returned for transparency


class Prediction(BaseModel):  # backend-only
    """
    A single prediction from the ML layer.

    Boundary: this model is NEVER written into the excursions table and NEVER
    carries a severity classification, regulatory citation, or disposition.
    Severity classification stays in app/engines/cold_chain.py against the
    YAML rule packs, unchanged by this layer.

    Every Prediction carries the full feature vector used so the operator can
    see why the model flagged this shipment (explainability via tooltip).
    The displayed probability is always the calibrated value (CalibratedClassifierCV).
    """
    id: str
    model_id: str
    model_version: str
    subject_type: str                               # "shipment" | "leg"
    subject_id: str
    predicted_at: datetime
    horizon_hours: float                            # 4.0 for excursion forecaster
    value: float                                    # calibrated P(breach) 0–1
    confidence: float                               # same as value for binary classifier
    features: dict[str, Union[float, int, str]]    # feature vector used
    baseline_value: float                           # B1 heuristic output for same input
