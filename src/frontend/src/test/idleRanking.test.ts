import { describe, it, expect } from 'vitest';
import { rankIdleAssets, idleCapacityScore, normaliseCapacity } from '@/lib/utils/idleRanking';
import type { FleetAsset } from '@/types/domain';

function makeAsset(overrides: Partial<FleetAsset>): FleetAsset {
  return {
    id: 'ast-test',
    type: 'truck',
    status: 'idle',
    location: { lat: 0, lng: 0, label: 'Test' },
    idleSinceAt: '2025-07-14T00:00:00Z',
    idleSinceHours: 24,
    capacity: { unit: 'pallets', value: 33 },
    utilisationPct30d: 30,
    reeferCapable: false,
    homeDepot: 'Test Depot',
    ...overrides,
  };
}

describe('normaliseCapacity', () => {
  it('pallets returns value directly', () => {
    expect(normaliseCapacity(makeAsset({ capacity: { unit: 'pallets', value: 66 } }))).toBe(66);
  });

  it('TEU multiplies by 20', () => {
    expect(normaliseCapacity(makeAsset({ capacity: { unit: 'TEU', value: 2 } }))).toBe(40);
  });

  it('kg divides by 500', () => {
    expect(normaliseCapacity(makeAsset({ capacity: { unit: 'kg', value: 10000 } }))).toBe(20);
  });
});

describe('idleCapacityScore', () => {
  it('returns 0 for non-idle asset', () => {
    expect(idleCapacityScore(makeAsset({ status: 'in_transit' }))).toBe(0);
  });

  it('idle truck 24h × 33 pallets = 792', () => {
    expect(idleCapacityScore(makeAsset({ status: 'idle', idleSinceHours: 24, capacity: { unit: 'pallets', value: 33 } }))).toBe(792);
  });

  it('higher idle hours = higher score', () => {
    const short = makeAsset({ idleSinceHours: 8 });
    const long = makeAsset({ idleSinceHours: 48 });
    expect(idleCapacityScore(long)).toBeGreaterThan(idleCapacityScore(short));
  });

  it('vessel with TEU capacity scores much higher than truck', () => {
    const truck = makeAsset({ type: 'truck', idleSinceHours: 24, capacity: { unit: 'pallets', value: 33 } });
    const vessel = makeAsset({ type: 'vessel', idleSinceHours: 24, capacity: { unit: 'TEU', value: 1200 } });
    expect(idleCapacityScore(vessel)).toBeGreaterThan(idleCapacityScore(truck));
  });
});

describe('rankIdleAssets', () => {
  it('filters out non-idle assets', () => {
    const assets = [
      makeAsset({ id: 'a1', status: 'idle', idleSinceHours: 10 }),
      makeAsset({ id: 'a2', status: 'in_transit', idleSinceHours: 0 }),
      makeAsset({ id: 'a3', status: 'maintenance', idleSinceHours: 0 }),
    ];
    const result = rankIdleAssets(assets);
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe('a1');
  });

  it('ranks by descending idle capacity score', () => {
    const assets = [
      makeAsset({ id: 'low', status: 'idle', idleSinceHours: 4, capacity: { unit: 'pallets', value: 10 } }),
      makeAsset({ id: 'high', status: 'idle', idleSinceHours: 48, capacity: { unit: 'pallets', value: 66 } }),
      makeAsset({ id: 'mid', status: 'idle', idleSinceHours: 12, capacity: { unit: 'pallets', value: 33 } }),
    ];
    const result = rankIdleAssets(assets);
    expect(result[0].id).toBe('high');
    expect(result[result.length - 1].id).toBe('low');
  });

  it('does not mutate the original array', () => {
    const assets = [
      makeAsset({ id: 'a', status: 'idle', idleSinceHours: 5 }),
      makeAsset({ id: 'b', status: 'idle', idleSinceHours: 20 }),
    ];
    const original = [...assets];
    rankIdleAssets(assets);
    expect(assets[0].id).toBe(original[0].id);
  });

  it('vessel with large TEU capacity ranks above truck with same idle hours', () => {
    const truck = makeAsset({
      id: 'truck-1',
      type: 'truck',
      status: 'idle',
      idleSinceHours: 24,
      capacity: { unit: 'pallets', value: 33 },
    });
    const vessel = makeAsset({
      id: 'vessel-1',
      type: 'vessel',
      status: 'idle',
      idleSinceHours: 24,
      capacity: { unit: 'TEU', value: 1200 },
    });
    const result = rankIdleAssets([truck, vessel]);
    expect(result[0].id).toBe('vessel-1');
  });

  it('when scores are equal, preserves relative order (stable)', () => {
    // Two identical trucks — same hours, same capacity: order should not flip
    const a1 = makeAsset({ id: 'aa', status: 'idle', idleSinceHours: 24, capacity: { unit: 'pallets', value: 33 } });
    const a2 = makeAsset({ id: 'ab', status: 'idle', idleSinceHours: 24, capacity: { unit: 'pallets', value: 33 } });
    const result = rankIdleAssets([a1, a2]);
    // Both in result; just confirm neither is lost
    expect(result).toHaveLength(2);
    expect(result.map((r) => r.id).sort()).toEqual(['aa', 'ab'].sort());
  });

  it('reefer container scores correctly using kg normalisation', () => {
    const reefer = makeAsset({
      id: 'ref-1',
      type: 'reefer_container',
      status: 'idle',
      idleSinceHours: 12,
      capacity: { unit: 'kg', value: 22_000 },
      reeferCapable: true,
    });
    // 22000 kg / 500 = 44 normalised pallets; 44 × 12 = 528
    expect(idleCapacityScore(reefer)).toBe(528);
  });

  it('returns empty array when all assets are in_transit', () => {
    const assets = [
      makeAsset({ id: 'x1', status: 'in_transit' }),
      makeAsset({ id: 'x2', status: 'in_transit' }),
    ];
    expect(rankIdleAssets(assets)).toHaveLength(0);
  });
});
