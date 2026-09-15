// ─── Primitives ──────────────────────────────────────────────────────────────

export type Mode = 'ocean' | 'air' | 'road' | 'rail';
export type Severity = 'informational' | 'minor' | 'major' | 'critical';
export type DisruptionType =
  | 'weather'
  | 'labour_action'
  | 'geopolitical'
  | 'congestion'
  | 'infrastructure'
  | 'customs';

export interface GeoPoint {
  lat: number;
  lng: number;
  label: string;
  unlocode?: string;
}

// ─── Shipment & Leg ──────────────────────────────────────────────────────────

export type LegStatus = 'completed' | 'in_transit' | 'scheduled' | 'blocked';

export interface Leg {
  id: string;
  sequence: number;
  mode: Mode;
  carrier: string;
  from: GeoPoint;
  to: GeoPoint;
  departsAt: string; // ISO UTC
  arrivesAt: string; // ISO UTC
  status: LegStatus;
}

export interface Cargo {
  description: string;
  valueUsd: number;
  isColdChain: boolean;
  tempRangeC?: { min: number; max: number }; // e.g. 2–8 for vaccines
  regulatoryRegime?: 'GDP' | 'WHO_PQS' | 'USP_1079' | 'FSMA';
}

export type ShipmentStatus = 'on_track' | 'at_risk' | 'delayed' | 'exception';

export interface Shipment {
  id: string;
  reference: string;
  shipper: string;
  consignee: string;
  origin: GeoPoint;
  destination: GeoPoint;
  legs: Leg[];
  cargo: Cargo;
  etaOriginal: string; // ISO UTC
  etaProjected: string; // ISO UTC
  status: ShipmentStatus;
  impactedBy: string[]; // disruption ids
  riskScore: number; // 0–100
}

// ─── Disruption ──────────────────────────────────────────────────────────────

export type DisruptionArea =
  | { center: GeoPoint; radiusKm: number }
  | { polygon: [number, number][] };

export interface Disruption {
  id: string;
  type: DisruptionType;
  headline: string;
  detail: string;
  severity: Severity;
  startedAt: string; // ISO UTC
  expectedResolutionAt: string | null; // ISO UTC
  confidence: number; // 0–1
  source: string;
  affectedArea: DisruptionArea;
  affectedNodes: string[]; // UN/LOCODEs
}

// ─── Reroute ─────────────────────────────────────────────────────────────────

export type ColdChainContinuity = 'maintained' | 'at_risk' | 'broken';
export type RerouteFeasibility = 'confirmed' | 'likely' | 'speculative';

export interface RerouteOption {
  id: string;
  shipmentId: string;
  summary: string;
  replacesLegIds: string[];
  newLegs: Leg[];
  deltaDays: number; // negative = recovers time
  deltaCostUsd: number;
  co2DeltaKg: number;
  coldChainContinuity: ColdChainContinuity;
  coldChainContinuityReason?: string; // why continuity is at_risk or broken
  feasibility: RerouteFeasibility;
  constraints: string[];
  rationale: string;
  recommended: boolean;
}

// ─── Fleet ───────────────────────────────────────────────────────────────────

export type AssetType = 'truck' | 'trailer' | 'container' | 'reefer_container' | 'vessel';
export type AssetStatus = 'idle' | 'in_transit' | 'maintenance' | 'reserved';

export interface FleetAsset {
  id: string;
  type: AssetType;
  status: AssetStatus;
  location: GeoPoint;
  idleSinceAt: string; // ISO UTC (source of truth)
  idleSinceHours: number; // derived
  capacity: { unit: 'TEU' | 'pallets' | 'kg'; value: number };
  utilisationPct30d: number;
  reeferCapable: boolean;
  homeDepot: string;
}

export interface RedeploymentMatch {
  assetId: string;
  shipmentId: string;
  distanceKm: number;
  hoursToPosition: number;
  utilisationGainPct: number;
  rationale: string;
  generatedAt: string; // ISO UTC — so operator can judge staleness
}

// ─── Cold Chain / Sensors ────────────────────────────────────────────────────

export interface SensorReading {
  shipmentId: string;
  sensorId: string;
  legId: string;
  timestamp: string; // ISO UTC
  tempC: number;
  humidityPct?: number;
  /**
   * NOTE: doorOpen is a boolean snapshot at reading time.
   * Duration of door-open events cannot be derived from a single boolean —
   * correlate with preceding reading's doorOpen state and Δt to estimate.
   */
  doorOpen?: boolean;
}

/**
 * Represents a gap in sensor data (no reading received).
 * The UI must render this as a literal gap in the temperature trace,
 * not interpolate across it.
 */
export interface SensorGap {
  shipmentId: string;
  sensorId: string;
  legId: string;
  gapStartAt: string; // ISO UTC — last known reading before gap
  gapEndAt: string; // ISO UTC — first reading after gap
  durationMinutes: number;
}

export type SensorEvent = SensorReading | SensorGap;

export function isSensorGap(e: SensorEvent): e is SensorGap {
  return 'gapStartAt' in e;
}

export type ExcursionDisposition =
  | 'release'
  | 'quarantine_pending_QA'
  | 'reject';

export interface Excursion {
  id: string;
  shipmentId: string;
  legId: string;
  startedAt: string; // ISO UTC
  endedAt: string | null; // null = still open
  peakTempC: number;
  minutesOutOfRange: number;
  /** Σ(|T_i − T_limit| × Δt_minutes) for each reading outside range */
  degreeMinutes: number;
  meanKineticTempC: number;
  severity: Severity;
  /** e.g. "GDP Annex 5.5 — excursion >2h above 8°C" */
  regulatoryBasis: string;
  disposition: ExcursionDisposition;
  evidenceReadingIds: string[];
  detectedBeforeDelivery: boolean;
}

// ─── Priority Queue item (cross-type, for Control Tower) ─────────────────────

export type PriorityItemKind =
  | 'shipment_exception'
  | 'excursion'
  | 'idle_asset'
  /** ML prediction — dashed visual treatment, no regulatory citation */
  | 'predicted_risk';

export interface PriorityItem {
  id: string;
  kind: PriorityItemKind;
  refId: string; // shipmentId, excursionId, or assetId
  headline: string;
  stake: string; // plain text: "$420K cargo at risk" or "14h idle · 26 pallets"
  severity: Severity;
  href: string;
  updatedAt: string; // ISO UTC
}

// ─── ML Predictions ───────────────────────────────────────────────────────────
// Backend-only at serving time; frontend receives these via /api/v1/predictions/*
//
// VISUAL CONTRACT:
//   - Dashed/hatched badge, never solid
//   - Show probability + horizon: "68% chance of breach within 4h"
//   - NO regulatory citation ever
//   - Below 50% confidence: watch item (informational), not alert
//   - Forecast band on temperature chart: dashed forward-projected line
//   - Tooltip shows top contributing features from model card (static)

export interface Prediction {
  id: string;
  modelId: string;
  modelVersion: string;
  subjectType: 'shipment' | 'leg';
  subjectId: string;
  predictedAt: string; // ISO UTC
  horizonHours: number; // 4.0 for excursion forecaster
  /** Calibrated P(breach), 0–1. This is the value displayed to the operator. */
  value: number;
  confidence: number;
  features: Record<string, number | string>;
  baselineValue: number;
}
