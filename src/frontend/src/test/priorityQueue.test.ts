import { describe, it, expect } from 'vitest';
import { buildPriorityQueue } from '@/lib/utils/priorityQueue';
import type { Shipment, Excursion, FleetAsset } from '@/types/domain';

// ─── Minimal fixtures ─────────────────────────────────────────────────────────

function makeShipment(overrides: Partial<Shipment>): Shipment {
  return {
    id: 's1',
    reference: 'REF-001',
    shipper: 'Shipper Co',
    consignee: 'Consignee Co',
    origin: { lat: 0, lng: 0, label: 'Origin' },
    destination: { lat: 1, lng: 1, label: 'Dest' },
    legs: [],
    cargo: { description: 'Electronics', valueUsd: 100_000, isColdChain: false },
    etaOriginal: '2025-07-15T10:00:00Z',
    etaProjected: '2025-07-15T10:00:00Z',
    status: 'on_track',
    impactedBy: [],
    riskScore: 10,
    ...overrides,
  };
}

function makeExcursion(overrides: Partial<Excursion>): Excursion {
  return {
    id: 'exc-1',
    shipmentId: 's1',
    legId: 'leg-1',
    startedAt: '2025-07-14T02:00:00Z',
    endedAt: null,
    peakTempC: 12,
    minutesOutOfRange: 300,
    degreeMinutes: 250,
    meanKineticTempC: 10.5,
    severity: 'critical',
    regulatoryBasis: 'GDP Annex 5.5',
    disposition: 'quarantine_pending_QA',
    evidenceReadingIds: ['r1', 'r2'],
    detectedBeforeDelivery: true,
    ...overrides,
  };
}

function makeAsset(overrides: Partial<FleetAsset>): FleetAsset {
  return {
    id: 'ast-1',
    type: 'truck',
    status: 'idle',
    location: { lat: 0, lng: 0, label: 'Hamburg' },
    idleSinceAt: '2025-07-13T10:00:00Z',
    idleSinceHours: 24,
    capacity: { unit: 'pallets', value: 33 },
    utilisationPct30d: 30,
    reeferCapable: false,
    homeDepot: 'Hamburg Depot',
    ...overrides,
  };
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('buildPriorityQueue', () => {
  it('returns empty array when all inputs are empty', () => {
    expect(buildPriorityQueue([], [], [])).toEqual([]);
  });

  it('excludes on_track shipments', () => {
    const shipments = [makeShipment({ id: 's1', status: 'on_track' })];
    const result = buildPriorityQueue(shipments, [], []);
    expect(result).toHaveLength(0);
  });

  it('includes exception and delayed shipments', () => {
    const shipments = [
      makeShipment({ id: 's1', status: 'exception', etaProjected: '2025-07-16T10:00:00Z' }),
      makeShipment({ id: 's2', status: 'delayed', etaProjected: '2025-07-17T10:00:00Z' }),
      makeShipment({ id: 's3', status: 'on_track' }),
    ];
    const result = buildPriorityQueue(shipments, [], []);
    expect(result).toHaveLength(2);
    const ids = result.map((r) => r.refId);
    expect(ids).toContain('s1');
    expect(ids).toContain('s2');
  });

  it('open critical excursion sorts before minor shipment exception', () => {
    // Shipment is at_risk (→ minor severity); excursion is critical.
    // Critical must sort above minor regardless of updatedAt.
    const shipments = [
      makeShipment({ id: 's1', status: 'at_risk', etaProjected: '2025-07-16T10:00:00Z' }),
    ];
    const excursions = [
      makeExcursion({ id: 'exc-1', shipmentId: 's1', severity: 'critical', endedAt: null }),
    ];
    const result = buildPriorityQueue(shipments, excursions, []);
    expect(result[0].kind).toBe('excursion');
    expect(result[0].refId).toBe('exc-1');
  });

  it('critical severity sorts before major', () => {
    const shipments = [
      makeShipment({ id: 's1', status: 'exception', etaProjected: '2025-07-16T10:00:00Z' }),
      makeShipment({ id: 's2', status: 'delayed', etaProjected: '2025-07-18T10:00:00Z' }),
    ];
    const result = buildPriorityQueue(shipments, [], []);
    const kinds = result.map((r) => r.severity);
    expect(kinds[0]).toBe('critical');
  });

  it('idle assets sort after excursions (critical excursion always beats idle_asset)', () => {
    // Excursion is critical; idle asset gets at most major (idleSinceHours=72>48).
    // Critical excursion must appear before the idle_asset in the sorted result.
    const shipments = [makeShipment({ id: 's1', status: 'at_risk', etaProjected: '2025-07-16T10:00:00Z' })];
    const excursions = [makeExcursion({ id: 'exc-1', shipmentId: 's1', severity: 'critical', endedAt: null })];
    const fleet = [makeAsset({ id: 'ast-1', idleSinceHours: 72 })];
    const result = buildPriorityQueue(shipments, excursions, fleet);
    const excIdx = result.findIndex((r) => r.kind === 'excursion');
    const assetIdx = result.findIndex((r) => r.kind === 'idle_asset');
    expect(excIdx).toBeGreaterThanOrEqual(0);
    if (assetIdx !== -1) {
      expect(excIdx).toBeLessThan(assetIdx);
    }
  });

  it('excursion item has correct href pointing to cold-chain page', () => {
    const shipments = [makeShipment({ id: 's1', status: 'exception', etaProjected: '2025-07-16T10:00:00Z' })];
    const excursions = [makeExcursion({ id: 'exc-42', shipmentId: 's1' })];
    const result = buildPriorityQueue(shipments, excursions, []);
    const item = result.find((r) => r.kind === 'excursion');
    expect(item?.href).toBe('/cold-chain#exc-42');
  });

  it('each item has required fields: id, kind, refId, headline, stake, severity, href, updatedAt', () => {
    const shipments = [makeShipment({ id: 's1', status: 'delayed', etaProjected: '2025-07-16T10:00:00Z' })];
    const result = buildPriorityQueue(shipments, [], []);
    const item = result[0];
    expect(item.id).toBeTruthy();
    expect(item.kind).toBeTruthy();
    expect(item.refId).toBeTruthy();
    expect(item.headline).toBeTruthy();
    expect(item.stake).toBeTruthy();
    expect(item.severity).toBeTruthy();
    expect(item.href).toBeTruthy();
    expect(item.updatedAt).toBeTruthy();
  });

  it('skips excursion whose shipmentId has no matching shipment', () => {
    const excursions = [makeExcursion({ id: 'exc-orphan', shipmentId: 'no-such-shipment' })];
    const result = buildPriorityQueue([], excursions, []);
    expect(result).toHaveLength(0);
  });
});
