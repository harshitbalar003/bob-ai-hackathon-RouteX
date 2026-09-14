/**
 * API adapter — hits the backend when VITE_DATA_SOURCE=api.
 * All methods follow the same DataAdapter interface as the mock adapter.
 * Components never call fetch directly.
 *
 * Error handling:
 *  - 5xx: surfaces the backend error message — never silently falls back to mock.
 *  - Network error (connection refused): tells the operator what command to run.
 */
import type { DataAdapter } from './types';

const BASE = (import.meta.env.VITE_API_BASE_URL ?? '/api') + '/v1';

async function get<T>(path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`);
  } catch (err) {
    // Connection refused or DNS failure
    const msg =
      err instanceof TypeError && err.message.includes('fetch')
        ? `Cannot reach backend at ${BASE}${path}.\n` +
          'Start the backend with: cd src/backend && uvicorn app.main:app --reload --port 8000'
        : String(err);
    throw new Error(msg);
  }
  if (!res.ok) {
    const body = await res.text().catch(() => '(no body)');
    throw new Error(`API error ${res.status} on ${path}: ${body}`);
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

  getFleetAssets: () => get('/fleet/idle'),
  getRedeploymentMatches: () => get('/fleet/redeployments'),

  getSensorReadings: async (id) => {
    const data = await get<{ readings: unknown[]; gaps: unknown[] }>(`/shipments/${id}/readings`);
    return data.readings as import('@/types/domain').SensorReading[];
  },
  getSensorGaps: async (id) => {
    const data = await get<{ readings: unknown[]; gaps: unknown[] }>(`/shipments/${id}/readings`);
    return data.gaps as import('@/types/domain').SensorGap[];
  },
  getExcursions: () => get('/cold-chain/excursions'),
  getExcursion: (id) => get(`/cold-chain/excursions/${id}`),

  getPriorityQueue: async () => {
    const data = await get<{ items: unknown[] }>('/priority-queue');
    return data.items as import('@/types/domain').PriorityItem[];
  },
};
