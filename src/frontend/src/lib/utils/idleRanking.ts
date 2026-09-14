import type { FleetAsset } from '@/types/domain';

/**
 * Idle score for a fleet asset.
 *
 * Score = idleSinceHours × capacityNormalised
 *
 * Capacity is normalised to a common unit-agnostic value:
 *   TEU: × 20  (one TEU ≈ 20 tonne equivalent)
 *   pallets: × 1
 *   kg: ÷ 500  (1 pallet ≈ 500 kg)
 *
 * Higher score = more wasted capacity-hours = ranks first.
 */
export function idleCapacityScore(asset: FleetAsset): number {
  if (asset.status !== 'idle') return 0;
  const capacity = normaliseCapacity(asset);
  return asset.idleSinceHours * capacity;
}

export function normaliseCapacity(asset: FleetAsset): number {
  const { unit, value } = asset.capacity;
  switch (unit) {
    case 'TEU':
      return value * 20;
    case 'pallets':
      return value;
    case 'kg':
      return value / 500;
    default:
      return value;
  }
}

/**
 * Sorts fleet assets by idle capacity score descending.
 * Returns a new array; does not mutate input.
 */
export function rankIdleAssets(assets: FleetAsset[]): FleetAsset[] {
  return [...assets]
    .filter((a) => a.status === 'idle')
    .sort((a, b) => idleCapacityScore(b) - idleCapacityScore(a));
}
