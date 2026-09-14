import React, { useState, useMemo } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { formatDistanceToNow, format } from 'date-fns';
import { useDisruption, useShipmentsByDisruption } from '@/lib/queries';
import { AsyncBoundary } from '@/components/ui/AsyncBoundary';
import { SkeletonTable, SkeletonCard } from '@/components/ui/Skeleton';
import { SeverityBadge, StatusBadge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import type { Shipment, Mode } from '@/types/domain';

const TYPE_LABEL: Record<string, string> = {
  weather: 'Weather event',
  labour_action: 'Labour action',
  geopolitical: 'Geopolitical',
  congestion: 'Congestion',
  infrastructure: 'Infrastructure failure',
  customs: 'Customs disruption',
};

const TYPE_ICON: Record<string, string> = {
  weather: '🌪',
  labour_action: '✊',
  geopolitical: '🚧',
  congestion: '⏳',
  infrastructure: '⚙',
  customs: '📋',
};

function delayHours(s: Shipment): number {
  return Math.round(
    (new Date(s.etaProjected).getTime() - new Date(s.etaOriginal).getTime()) / 3_600_000,
  );
}

interface Filters {
  mode: Mode | 'all';
  coldChainOnly: boolean;
  minValueK: number;
}

const MODES: { value: Mode | 'all'; label: string }[] = [
  { value: 'all', label: 'All modes' },
  { value: 'ocean', label: 'Ocean' },
  { value: 'air', label: 'Air' },
  { value: 'road', label: 'Road' },
  { value: 'rail', label: 'Rail' },
];

export function DisruptionDetail() {
  const { id } = useParams<{ id: string }>();
  const dis = useDisruption(id!);
  const impacted = useShipmentsByDisruption(id!);
  const navigate = useNavigate();

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [filters, setFilters] = useState<Filters>({
    mode: 'all',
    coldChainOnly: false,
    minValueK: 0,
  });

  // Filtered + sorted shipments
  const filtered = useMemo(() => {
    const all = impacted.data ?? [];
    return all
      .filter((s) => {
        if (filters.mode !== 'all' && !s.legs.some((l) => l.mode === filters.mode)) return false;
        if (filters.coldChainOnly && !s.cargo.isColdChain) return false;
        if (s.cargo.valueUsd < filters.minValueK * 1000) return false;
        return true;
      })
      .sort((a, b) => {
        // Exception/delayed first, then by value descending
        const statusOrder = { exception: 3, delayed: 2, at_risk: 1, on_track: 0 };
        const sd = (statusOrder[b.status] ?? 0) - (statusOrder[a.status] ?? 0);
        if (sd !== 0) return sd;
        return b.cargo.valueUsd - a.cargo.valueUsd;
      });
  }, [impacted.data, filters]);

  function toggleSelect(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function selectAll() {
    setSelected(new Set(filtered.map((s) => s.id)));
  }

  function clearSelection() {
    setSelected(new Set());
  }

  const blockedCount = filtered.filter((s) => s.legs.some((l) => l.status === 'blocked')).length;
  const coldChainCount = filtered.filter((s) => s.cargo.isColdChain).length;
  const totalValue = filtered.reduce((sum, s) => sum + s.cargo.valueUsd, 0);

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">

      {/* ── Disruption header ─────────────────────────────────────── */}
      <AsyncBoundary
        data={dis.data}
        isLoading={dis.isLoading}
        isError={dis.isError}
        error={dis.error as Error}
        onRetry={() => dis.refetch()}
        loadingFallback={<SkeletonCard />}
        emptyFallback={
          <div className="text-text-muted text-sm">
            Disruption not found.{' '}
            <Link to="/" className="text-accent-minor underline">
              Return to control tower
            </Link>
          </div>
        }
      >
        {(d) => (
          <div className="space-y-4">
            {/* Unconfirmed warning banner */}
            {d.confidence < 0.6 && (
              <div
                className="px-4 py-3 rounded border border-accent-disruption/40 bg-accent-disruption/8 flex items-start gap-3"
                role="alert"
              >
                <span className="text-accent-disruption shrink-0">▲</span>
                <div>
                  <p className="text-sm font-medium text-accent-disruption">
                    Low confidence — treat as unconfirmed
                  </p>
                  <p className="text-xs text-text-muted mt-0.5">
                    Source reports {Math.round(d.confidence * 100)}% confidence. Verify with{' '}
                    <span className="text-text-primary">{d.source}</span> before acting.
                  </p>
                </div>
              </div>
            )}

            {/* Type + severity row */}
            <div className="flex items-center gap-3 flex-wrap">
              <SeverityBadge severity={d.severity} />
              <span className="text-sm text-text-muted">
                {TYPE_ICON[d.type] ?? ''} {TYPE_LABEL[d.type] ?? d.type}
              </span>
              <span className="text-xs text-text-muted">·</span>
              <span className="text-xs text-text-muted">{d.source}</span>
            </div>

            {/* Headline */}
            <h1 className="text-xl font-medium text-text-primary">{d.headline}</h1>
            <p className="text-sm text-text-muted leading-relaxed">{d.detail}</p>

            {/* Meta grid */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {[
                {
                  label: 'Started',
                  value: formatDistanceToNow(new Date(d.startedAt), { addSuffix: true }),
                  sub: format(new Date(d.startedAt), 'dd MMM HH:mm') + ' UTC',
                },
                {
                  label: 'Expected resolution',
                  value: d.expectedResolutionAt
                    ? format(new Date(d.expectedResolutionAt), 'dd MMM HH:mm') + ' UTC'
                    : 'Unknown',
                  sub: d.expectedResolutionAt
                    ? formatDistanceToNow(new Date(d.expectedResolutionAt), { addSuffix: true })
                    : undefined,
                },
                {
                  label: 'Confidence',
                  value: `${Math.round(d.confidence * 100)}%`,
                  sub: d.confidence < 0.6 ? 'Unconfirmed' : 'Confirmed',
                  valueClass: d.confidence < 0.6 ? 'text-accent-disruption' : 'text-accent-tracking',
                },
                {
                  label: 'Source',
                  value: d.source,
                },
              ].map(({ label, value, sub, valueClass }) => (
                <div
                  key={label}
                  className="bg-surface-raised rounded p-3 border border-surface-border"
                >
                  <div className="text-xs text-text-muted mb-1">{label}</div>
                  <div className={`text-sm font-medium ${valueClass ?? 'text-text-primary'}`}>
                    {value}
                  </div>
                  {sub && <div className="text-xs text-text-muted mt-0.5">{sub}</div>}
                </div>
              ))}
            </div>

            {/* Affected nodes */}
            {d.affectedNodes.length > 0 && (
              <div>
                <div className="text-xs text-text-muted mb-1.5">Affected nodes</div>
                <div className="flex flex-wrap gap-1.5">
                  {d.affectedNodes.map((n) => (
                    <span
                      key={n}
                      className="px-2 py-0.5 rounded text-xs bg-surface-raised border border-surface-border text-text-primary font-mono-sensor"
                    >
                      {n}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </AsyncBoundary>

      {/* ── Impacted shipments ────────────────────────────────────── */}
      <div>
        {/* Section header */}
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <div>
            <h2 className="text-base font-medium text-text-primary">
              Impacted shipments
              {impacted.data && (
                <span className="ml-2 text-text-muted text-sm font-normal">
                  ({filtered.length}{filtered.length !== impacted.data.length ? ` of ${impacted.data.length}` : ''})
                </span>
              )}
            </h2>
            {impacted.data && (
              <p className="text-xs text-text-muted mt-0.5">
                {blockedCount > 0 && (
                  <span className="text-accent-critical mr-3">{blockedCount} blocked</span>
                )}
                {coldChainCount > 0 && (
                  <span className="text-accent-tracking mr-3">{coldChainCount} cold chain</span>
                )}
                <span className="tabular-nums">
                  Total value at risk: ${(totalValue / 1_000_000).toFixed(1)}M
                </span>
              </p>
            )}
          </div>
          {selected.size > 0 && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-text-muted">{selected.size} selected</span>
              <Button variant="ghost" size="sm" onClick={clearSelection}>
                Clear
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={() => {
                  const first = [...selected][0];
                  navigate(`/reroutes?shipmentId=${first}`);
                }}
              >
                Review reroutes →
              </Button>
            </div>
          )}
        </div>

        {/* Filter controls */}
        <div className="flex items-center gap-3 mb-3 flex-wrap">
          <select
            aria-label="Filter by mode"
            value={filters.mode}
            onChange={(e) =>
              setFilters((f) => ({ ...f, mode: e.target.value as Mode | 'all' }))
            }
            className="bg-surface-raised border border-surface-border text-text-primary text-xs rounded px-2.5 py-1 outline-none focus-visible:ring-2 focus-visible:ring-accent-minor"
          >
            {MODES.map(({ value, label }) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>

          <label className="flex items-center gap-1.5 text-xs text-text-muted cursor-pointer">
            <input
              type="checkbox"
              checked={filters.coldChainOnly}
              onChange={(e) =>
                setFilters((f) => ({ ...f, coldChainOnly: e.target.checked }))
              }
              className="rounded accent-accent-tracking"
            />
            ❄ Cold chain only
          </label>

          <label className="flex items-center gap-1.5 text-xs text-text-muted cursor-pointer">
            Min value
            <select
              aria-label="Minimum cargo value"
              value={filters.minValueK}
              onChange={(e) =>
                setFilters((f) => ({ ...f, minValueK: Number(e.target.value) }))
              }
              className="bg-surface-raised border border-surface-border text-text-primary text-xs rounded px-2 py-0.5 ml-1 outline-none focus-visible:ring-2 focus-visible:ring-accent-minor"
            >
              <option value={0}>Any</option>
              <option value={100}>$100K+</option>
              <option value={500}>$500K+</option>
              <option value={1000}>$1M+</option>
            </select>
          </label>

          {filtered.length > 0 && (
            <button
              onClick={selectAll}
              className="text-xs text-accent-minor hover:underline focus-visible:underline outline-none ml-auto"
            >
              Select all {filtered.length}
            </button>
          )}
        </div>

        {/* Table */}
        <div className="bg-surface-raised rounded border border-surface-border overflow-hidden">
          <AsyncBoundary
            data={filtered}
            isLoading={impacted.isLoading}
            isError={impacted.isError}
            error={impacted.error as Error}
            onRetry={() => impacted.refetch()}
            isEmpty={(d) => d.length === 0}
            loadingFallback={<SkeletonTable rows={6} />}
            emptyFallback={
              <div className="p-8 text-center text-text-muted text-sm">
                {impacted.data?.length === 0
                  ? 'No shipments are impacted by this disruption.'
                  : 'No shipments match the current filters.'}
              </div>
            }
          >
            {(rows) => (
              <div className="overflow-x-auto">
                <table className="w-full text-sm border-collapse">
                  <caption className="sr-only">
                    Shipments impacted by this disruption
                  </caption>
                  <thead className="sticky top-0 bg-surface-base border-b border-surface-border z-10">
                    <tr>
                      <th scope="col" className="py-2 px-3 w-8">
                        <span className="sr-only">Select</span>
                      </th>
                      {[
                        { key: 'ref', label: 'Reference', align: 'left' },
                        { key: 'cargo', label: 'Cargo', align: 'left' },
                        { key: 'value', label: 'Value', align: 'right' },
                        { key: 'status', label: 'Status', align: 'left' },
                        { key: 'etaOrig', label: 'Original ETA', align: 'right' },
                        { key: 'etaProj', label: 'Projected ETA', align: 'right' },
                        { key: 'delay', label: 'Delay', align: 'right' },
                        { key: 'blocked', label: 'Blocked leg', align: 'left' },
                        { key: 'reroute', label: 'Reroute', align: 'left' },
                      ].map(({ key, label, align }) => (
                        <th
                          key={key}
                          scope="col"
                          className={`py-2 px-3 text-xs font-medium text-text-muted
                            ${align === 'right' ? 'text-right' : 'text-left'}`}
                        >
                          {label}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-surface-border">
                    {rows.map((s) => {
                      const isSelected = selected.has(s.id);
                      const delay = delayHours(s);
                      const blockedLeg = s.legs.find((l) => l.status === 'blocked');
                      const isException = s.status === 'exception';
                      return (
                        <tr
                          key={s.id}
                          className={`transition-colors duration-75 cursor-pointer
                            ${isException
                              ? 'bg-accent-critical/5 hover:bg-accent-critical/10'
                              : isSelected
                              ? 'bg-accent-minor/8 hover:bg-accent-minor/12'
                              : 'hover:bg-surface-raised/50'}
                          `}
                          onClick={() => toggleSelect(s.id)}
                        >
                          <td className="py-2.5 px-3">
                            <input
                              type="checkbox"
                              checked={isSelected}
                              onChange={() => toggleSelect(s.id)}
                              onClick={(e) => e.stopPropagation()}
                              aria-label={`Select ${s.reference}`}
                              className="rounded accent-accent-minor"
                            />
                          </td>
                          <td className="py-2.5 px-3">
                            <Link
                              to={`/shipments/${s.id}`}
                              className="text-accent-minor hover:underline focus-visible:underline outline-none"
                              onClick={(e) => e.stopPropagation()}
                            >
                              {s.reference}
                            </Link>
                          </td>
                          <td className="py-2.5 px-3 text-text-muted text-xs">
                            {s.cargo.description}
                            {s.cargo.isColdChain && (
                              <span className="ml-1 text-accent-tracking">❄</span>
                            )}
                          </td>
                          <td className="py-2.5 px-3 text-right tabular-nums text-sm">
                            ${(s.cargo.valueUsd / 1000).toFixed(0)}K
                          </td>
                          <td className="py-2.5 px-3">
                            <StatusBadge
                              label={s.status.replace('_', ' ')}
                              variant={s.status as 'on_track' | 'at_risk' | 'delayed' | 'exception' | 'neutral'}
                            />
                          </td>
                          <td className="py-2.5 px-3 text-right tabular-nums text-xs text-text-muted">
                            {format(new Date(s.etaOriginal), 'dd MMM HH:mm')} UTC
                          </td>
                          <td className="py-2.5 px-3 text-right tabular-nums text-xs text-text-primary">
                            {format(new Date(s.etaProjected), 'dd MMM HH:mm')} UTC
                          </td>
                          <td className="py-2.5 px-3 text-right tabular-nums text-sm">
                            <span className={delay > 0 ? 'text-accent-disruption font-medium' : 'text-text-muted'}>
                              {delay > 0 ? `+${delay}h` : '—'}
                            </span>
                          </td>
                          <td className="py-2.5 px-3 text-xs text-text-muted">
                            {blockedLeg ? (
                              <span className="text-accent-critical">
                                {blockedLeg.from.label} → {blockedLeg.to.label}
                              </span>
                            ) : '—'}
                          </td>
                          <td className="py-2.5 px-3">
                            <Link
                              to={`/reroutes?shipmentId=${s.id}`}
                              className="text-xs text-accent-minor hover:underline focus-visible:underline outline-none"
                              onClick={(e) => e.stopPropagation()}
                            >
                              Options →
                            </Link>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </AsyncBoundary>
        </div>
      </div>
    </div>
  );
}
