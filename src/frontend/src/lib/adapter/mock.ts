import type { DataAdapter } from './types';
import type {
  Shipment,
  Disruption,
  FleetAsset,
  RedeploymentMatch,
  RerouteOption,
  SensorReading,
  SensorGap,
  Excursion,
} from '@/types/domain';
import shipmentsData from '@/data/fixtures/shipments.json';
import disruptionsData from '@/data/fixtures/disruptions.json';
import fleetData from '@/data/fixtures/fleet.json';
import reroutesData from '@/data/fixtures/reroute-options.json';
import sensorReadingsData from '@/data/fixtures/sensor-readings.json';
import sensorGapsData from '@/data/fixtures/sensor-gaps.json';
import excursionsData from '@/data/fixtures/excursions.json';
import { buildPriorityQueue } from '@/lib/utils/priorityQueue';

const shipments = shipmentsData as Shipment[];
const disruptions = disruptionsData as Disruption[];
const fleet = fleetData as FleetAsset[];
const reroutes = reroutesData as RerouteOption[];
const sensorReadings = sensorReadingsData as SensorReading[];
const sensorGaps = sensorGapsData as SensorGap[];
const excursions = excursionsData as Excursion[];

function delay<T>(value: T, ms = 120): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms));
}

function notFound(entity: string, id: string): Promise<never> {
  return Promise.reject(new Error(`${entity} not found: ${id}`));
}

export const mockAdapter: DataAdapter = {
  getDisruptions: () => delay(disruptions),
  getDisruption: (id) => {
    const d = disruptions.find((x) => x.id === id);
    return d ? delay(d) : notFound('Disruption', id);
  },

  getShipments: () => delay(shipments),
  getShipment: (id) => {
    const s = shipments.find((x) => x.id === id);
    return s ? delay(s) : notFound('Shipment', id);
  },
  getShipmentsByDisruption: (disruptionId) =>
    delay(shipments.filter((s) => s.impactedBy.includes(disruptionId))),

  getRerouteOptions: (shipmentId) =>
    delay(reroutes.filter((r) => r.shipmentId === shipmentId)),
  getAllRerouteOptions: () => delay(reroutes),

  getFleetAssets: () => delay(fleet),
  getRedeploymentMatches: async () => {
    const matches = (await import('@/data/fixtures/redeployment-matches.json')).default as RedeploymentMatch[];
    return delay(matches);
  },

  getSensorReadings: (shipmentId) =>
    delay(sensorReadings.filter((r) => r.shipmentId === shipmentId)),
  getSensorGaps: (shipmentId) =>
    delay(sensorGaps.filter((g) => g.shipmentId === shipmentId)),
  getExcursions: () => delay(excursions),
  getExcursion: (id) => {
    const e = excursions.find((x) => x.id === id);
    return e ? delay(e) : notFound('Excursion', id);
  },

  getPriorityQueue: () =>
    delay(buildPriorityQueue(shipments, excursions, fleet)),
};
