/**
 * API adapter — hits the backend when VITE_DATA_SOURCE=api.
 * All methods follow the same DataAdapter interface as the mock adapter.
 * Components never call fetch directly.
 */
import type { DataAdapter } from './types';

const BASE = import.meta.env.VITE_API_BASE_URL ?? '/api';

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) {
    throw new Error(`API error ${res.status} on ${path}: ${await res.text()}`);
  }
  return res.json() as Promise<T>;
}

export const apiAdapter: DataAdapter = {
  getDisruptions: () => get('/disruptions'),
  getDisruption: (id) => get(`/disruptions/${id}`),

  getShipments: () => get('/shipments'),
  getShipment: (id) => get(`/shipments/${id}`),
  getShipmentsByDisruption: (id) => get(`/disruptions/${id}/shipments`),

  getRerouteOptions: (id) => get(`/shipments/${id}/reroutes`),
  getAllRerouteOptions: () => get('/reroutes'),

  getFleetAssets: () => get('/fleet'),
  getRedeploymentMatches: () => get('/fleet/redeployment-matches'),

  getSensorReadings: (id) => get(`/shipments/${id}/sensor-readings`),
  getSensorGaps: (id) => get(`/shipments/${id}/sensor-gaps`),
  getExcursions: () => get('/cold-chain/excursions'),
  getExcursion: (id) => get(`/cold-chain/excursions/${id}`),

  getPriorityQueue: () => get('/control-tower/priority-queue'),
};
