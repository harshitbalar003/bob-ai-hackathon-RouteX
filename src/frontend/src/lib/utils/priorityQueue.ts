import type { Shipment, Excursion, FleetAsset, PriorityItem, Severity } from '@/types/domain';
import { idleCapacityScore } from './idleRanking';
import { severityRank } from './severity';

function formatUsd(n: number): string {
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `$${Math.round(n / 1_000)}K`;
  return `$${n}`;
}

function delayhours(s: Shipment): number {
  const orig = new Date(s.etaOriginal).getTime();
  const proj = new Date(s.etaProjected).getTime();
  return Math.round((proj - orig) / 3_600_000);
}

export function buildPriorityQueue(
  shipments: Shipment[],
  excursions: Excursion[],
  fleet: FleetAsset[],
): PriorityItem[] {
  const items: PriorityItem[] = [];

  // Shipment exceptions
  for (const s of shipments) {
    if (s.status === 'on_track') continue;
    const delay = delayhours(s);
    const severity: Severity =
      s.status === 'exception' ? 'critical' :
      s.status === 'delayed' ? 'major' : 'minor';
    items.push({
      id: `ship-${s.id}`,
      kind: 'shipment_exception',
      refId: s.id,
      headline: `${s.reference} — ${s.cargo.description}`,
      stake: `${formatUsd(s.cargo.valueUsd)} cargo · +${delay}h delay`,
      severity,
      href: `/tower/shipments/${s.id}`,
      updatedAt: s.etaProjected,
    });
  }

  // Open and recent excursions
  for (const e of excursions) {
    const shipment = shipments.find((s) => s.id === e.shipmentId);
    if (!shipment) continue;
    const open = e.endedAt === null;
    items.push({
      id: `exc-${e.id}`,
      kind: 'excursion',
      refId: e.id,
      headline: `Temperature breach — ${shipment.reference}`,
      stake: `${formatUsd(shipment.cargo.valueUsd)} cargo · ${e.minutesOutOfRange}m out of range`,
      severity: e.severity,
      href: `/tower/cold-chain#${e.id}`,
      updatedAt: open ? e.startedAt : (e.endedAt ?? e.startedAt),
    });
  }

  // Idle assets (top 10 by capacity-hours)
  const idleAssets = fleet
    .filter((a) => a.status === 'idle')
    .sort((a, b) => idleCapacityScore(b) - idleCapacityScore(a))
    .slice(0, 10);

  for (const a of idleAssets) {
    items.push({
      id: `asset-${a.id}`,
      kind: 'idle_asset',
      refId: a.id,
      headline: `${a.type.replace('_', ' ')} idle — ${a.location.label}`,
      stake: `${a.idleSinceHours}h idle · ${a.capacity.value} ${a.capacity.unit}`,
      severity: a.idleSinceHours > 48 ? 'major' : 'minor',
      href: `/tower/fleet#${a.id}`,
      updatedAt: a.idleSinceAt,
    });
  }

  // Sort: critical first, then by severity, then by updatedAt descending
  return items.sort((a, b) => {
    const sd = severityRank(b.severity) - severityRank(a.severity);
    if (sd !== 0) return sd;
    return new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime();
  });
}
