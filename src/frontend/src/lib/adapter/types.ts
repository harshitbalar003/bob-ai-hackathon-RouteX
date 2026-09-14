import type {
  Shipment,
  Disruption,
  FleetAsset,
  RedeploymentMatch,
  RerouteOption,
  SensorReading,
  SensorGap,
  Excursion,
  PriorityItem,
} from '@/types/domain';

// ─── Adapter interface ────────────────────────────────────────────────────────
// All data flows through this interface. Components never know which
// implementation (mock or api) is active.

export interface DataAdapter {
  // Disruptions
  getDisruptions(): Promise<Disruption[]>;
  getDisruption(id: string): Promise<Disruption>;

  // Shipments
  getShipments(): Promise<Shipment[]>;
  getShipment(id: string): Promise<Shipment>;
  getShipmentsByDisruption(disruptionId: string): Promise<Shipment[]>;

  // Reroutes
  getRerouteOptions(shipmentId: string): Promise<RerouteOption[]>;
  getAllRerouteOptions(): Promise<RerouteOption[]>;

  // Fleet
  getFleetAssets(): Promise<FleetAsset[]>;
  getRedeploymentMatches(): Promise<RedeploymentMatch[]>;

  // Cold chain
  getSensorReadings(shipmentId: string): Promise<SensorReading[]>;
  getSensorGaps(shipmentId: string): Promise<SensorGap[]>;
  getExcursions(): Promise<Excursion[]>;
  getExcursion(id: string): Promise<Excursion>;

  // Priority queue (pre-ranked, ready for display)
  getPriorityQueue(): Promise<PriorityItem[]>;
}
