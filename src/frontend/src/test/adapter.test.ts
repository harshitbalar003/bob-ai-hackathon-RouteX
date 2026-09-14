/**
 * Adapter contract tests.
 * Verifies that the mock adapter returns data that conforms to the domain types
 * in domain.ts. This is the boundary test — if the mock adapter breaks the
 * contract, every component using TanStack Query hooks will silently render
 * wrong data.
 */
import { describe, it, expect } from 'vitest';
import { mockAdapter } from '@/lib/adapter/mock';

describe('mockAdapter — disruptions', () => {
  it('returns an array of disruptions', async () => {
    const result = await mockAdapter.getDisruptions();
    expect(Array.isArray(result)).toBe(true);
    expect(result.length).toBeGreaterThan(0);
  });

  it('each disruption has required fields', async () => {
    const disruptions = await mockAdapter.getDisruptions();
    for (const d of disruptions) {
      expect(typeof d.id).toBe('string');
      expect(typeof d.type).toBe('string');
      expect(typeof d.headline).toBe('string');
      expect(typeof d.severity).toBe('string');
      expect(typeof d.confidence).toBe('number');
      expect(d.confidence).toBeGreaterThanOrEqual(0);
      expect(d.confidence).toBeLessThanOrEqual(1);
    }
  });

  it('getDisruption returns correct disruption by id', async () => {
    const all = await mockAdapter.getDisruptions();
    const first = all[0];
    const fetched = await mockAdapter.getDisruption(first.id);
    expect(fetched.id).toBe(first.id);
  });

  it('getDisruption rejects for unknown id', async () => {
    await expect(mockAdapter.getDisruption('no-such-id')).rejects.toThrow('Disruption not found: no-such-id');
  });
});

describe('mockAdapter — shipments', () => {
  it('returns 120 shipments', async () => {
    const result = await mockAdapter.getShipments();
    expect(result).toHaveLength(120);
  });

  it('each shipment has required fields', async () => {
    const shipments = await mockAdapter.getShipments();
    for (const s of shipments) {
      expect(typeof s.id).toBe('string');
      expect(typeof s.reference).toBe('string');
      expect(Array.isArray(s.legs)).toBe(true);
      expect(typeof s.cargo.valueUsd).toBe('number');
      expect(typeof s.cargo.isColdChain).toBe('boolean');
      expect(['on_track', 'at_risk', 'delayed', 'exception']).toContain(s.status);
      expect(s.riskScore).toBeGreaterThanOrEqual(0);
      expect(s.riskScore).toBeLessThanOrEqual(100);
    }
  });

  it('getShipmentsByDisruption returns only shipments impacted by that disruption', async () => {
    const disruptions = await mockAdapter.getDisruptions();
    const disruptionId = disruptions[0].id;
    const impacted = await mockAdapter.getShipmentsByDisruption(disruptionId);
    for (const s of impacted) {
      expect(s.impactedBy).toContain(disruptionId);
    }
  });
});

describe('mockAdapter — fleet', () => {
  it('returns 40 fleet assets', async () => {
    const result = await mockAdapter.getFleetAssets();
    expect(result).toHaveLength(40);
  });

  it('each asset has required fields', async () => {
    const assets = await mockAdapter.getFleetAssets();
    for (const a of assets) {
      expect(typeof a.id).toBe('string');
      expect(['truck', 'trailer', 'container', 'reefer_container', 'vessel']).toContain(a.type);
      expect(['idle', 'in_transit', 'maintenance', 'reserved']).toContain(a.status);
      expect(typeof a.reeferCapable).toBe('boolean');
      expect(a.utilisationPct30d).toBeGreaterThanOrEqual(0);
      expect(a.utilisationPct30d).toBeLessThanOrEqual(100);
    }
  });
});

describe('mockAdapter — cold chain', () => {
  it('returns excursions array', async () => {
    const excursions = await mockAdapter.getExcursions();
    expect(Array.isArray(excursions)).toBe(true);
    expect(excursions.length).toBeGreaterThan(0);
  });

  it('each excursion has required fields', async () => {
    const excursions = await mockAdapter.getExcursions();
    for (const e of excursions) {
      expect(typeof e.id).toBe('string');
      expect(typeof e.shipmentId).toBe('string');
      expect(typeof e.minutesOutOfRange).toBe('number');
      expect(typeof e.degreeMinutes).toBe('number');
      expect(['informational', 'minor', 'major', 'critical']).toContain(e.severity);
      expect(['release', 'quarantine_pending_QA', 'reject']).toContain(e.disposition);
      expect(typeof e.detectedBeforeDelivery).toBe('boolean');
    }
  });

  it('returns sensor readings for a cold chain shipment', async () => {
    const readings = await mockAdapter.getSensorReadings('shp-101');
    expect(readings.length).toBeGreaterThan(0);
    for (const r of readings) {
      expect(r.shipmentId).toBe('shp-101');
      expect(typeof r.tempC).toBe('number');
    }
  });

  it('returns sensor gaps for shipment with a known gap', async () => {
    const gaps = await mockAdapter.getSensorGaps('shp-105');
    expect(gaps.length).toBeGreaterThan(0);
    const gap = gaps[0];
    expect(gap.shipmentId).toBe('shp-105');
    expect(typeof gap.gapStartAt).toBe('string');
    expect(typeof gap.gapEndAt).toBe('string');
  });
});

describe('mockAdapter — priority queue', () => {
  it('returns a non-empty priority queue', async () => {
    const queue = await mockAdapter.getPriorityQueue();
    expect(queue.length).toBeGreaterThan(0);
  });

  it('each item has kind, severity, headline, href', async () => {
    const queue = await mockAdapter.getPriorityQueue();
    for (const item of queue) {
      expect(['shipment_exception', 'excursion', 'idle_asset']).toContain(item.kind);
      expect(['informational', 'minor', 'major', 'critical']).toContain(item.severity);
      expect(typeof item.headline).toBe('string');
      expect(typeof item.href).toBe('string');
    }
  });

  it('first item in queue is not an idle_asset when excursions exist', async () => {
    const queue = await mockAdapter.getPriorityQueue();
    expect(queue[0].kind).not.toBe('idle_asset');
  });
});
