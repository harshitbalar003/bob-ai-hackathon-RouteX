import React, { useId } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { formatDistanceToNow, format } from 'date-fns';
import { useExcursions, useShipments } from '@/lib/queries';
import { AsyncBoundary } from '@/components/ui/AsyncBoundary';
import { SkeletonTable } from '@/components/ui/Skeleton';
import { SeverityBadge } from '@/components/ui/Badge';
import { formatSeverityLine, compareSeverity } from '@/lib/utils/severity';
import type { Excursion, Shipment } from '@/types/domain';

interface ExcursionRow {
  excursion: Excursion;
  shipment: Shipment | undefined;
}

const DISPOSITION_LABEL: Record<string, string> = {
  release: 'Release',
  quarantine_pending_QA: 'Quarantine — QA pending',
  reject: 'Reject',
};

const DISPOSITION_STYLE: Record<string, string> = {
  release: 'text-accent-tracking',
  quarantine_pending_QA: 'text-accent-disruption',
  reject: 'text-accent-critical',
};

function sortRows(rows: ExcursionRow[]): ExcursionRow[] {
  return [...rows].sort((a, b) => {
    const ae = a.excursion;
    const be = b.excursion;
    // 1. Open critical in-transit first — these are actionable
    const aUrgent = ae.endedAt === null && ae.severity === 'critical' ? 2
      : ae.endedAt === null ? 1 : 0;
    const bUrgent = be.endedAt === null && be.severity === 'critical' ? 2
      : be.endedAt === null ? 1 : 0;
    if (aUrgent !== bUrgent) return bUrgent - aUrgent;
    // 2. By severity descending
    const sd = compareSeverity(ae.severity, be.severity);
    if (sd !== 0) return sd;
    // 3. Actionable before delivery first
    if (ae.detectedBeforeDelivery !== be.detectedBeforeDelivery) {
      return ae.detectedBeforeDelivery ? -1 : 1;
    }
    // 4. Most recent first
    return new Date(be.startedAt).getTime() - new Date(ae.startedAt).getTime();
  });
}

/** Pulsing red dot for open breaches — respects prefers-reduced-motion */
function OpenBreachDot() {
  return (
    <span className="relative inline-flex" aria-hidden="true">
      <span className="w-2 h-2 rounded-full bg-accent-critical motion-safe:animate-ping absolute inline-flex opacity-60" />
      <span className="w-2 h-2 rounded-full bg-accent-critical relative inline-flex" />
    </span>
  );
}

function ExcursionTableRow({ row, isHighlighted }: { row: ExcursionRow; isHighlighted: boolean }) {
  const exc = row.excursion;
  const ship = row.shipment;
  const isOpenCritical = exc.endedAt === null && exc.severity === 'critical';
  const isOpen = exc.endedAt === null;

  const h = Math.floor(exc.minutesOutOfRange / 60);
  const m = exc.minutesOutOfRange % 60;
  const dur = h > 0 ? `${h}h ${m}m` : `${m}m`;

  return (
    <tr
      id={exc.id}
      className={`border-b border-surface-border transition-colors duration-75
        ${isOpenCritical
          ? 'bg-accent-critical/8 hover:bg-accent-critical/12'
          : 'hover:bg-surface-raised/40'}
        ${isHighlighted ? 'ring-1 ring-inset ring-accent-minor' : ''}`}
    >
      {/* Shipment reference */}
      <td className="py-2.5 px-3 text-sm">
        {ship ? (
          <Link
            to={`/shipments/${ship.id}`}
            className="text-accent-minor hover:underline focus-visible:underline outline-none"
          >
            {ship.reference}
          </Link>
        ) : (
          <span className="text-text-muted font-mono-sensor text-xs">{exc.shipmentId}</span>
        )}
        {ship?.cargo.isColdChain && (
          <span className="ml-1.5 text-[10px] text-accent-tracking">❄</span>
        )}
      </td>

      {/* Cargo value */}
      <td className="py-2.5 px-3 text-right tabular-nums text-sm">
        {ship ? `$${(ship.cargo.valueUsd / 1000).toFixed(0)}K` : '—'}
      </td>

      {/* Breach status */}
      <td className="py-2.5 px-3 text-sm">
        {isOpen ? (
          <span className="inline-flex items-center gap-1.5 text-accent-critical font-medium text-xs">
            <OpenBreachDot />
            Open — in transit
          </span>
        ) : (
          <span className="text-xs text-text-muted">
            Resolved {formatDistanceToNow(new Date(exc.endedAt!), { addSuffix: true })}
          </span>
        )}
      </td>

      {/* Severity — shape + label + driver */}
      <td className="py-2.5 px-3">
        <div className="space-y-0.5">
          <SeverityBadge severity={exc.severity} />
          <div className="text-[10px] text-text-muted leading-snug font-mono-sensor">
            {formatSeverityLine(exc)}
          </div>
        </div>
      </td>

      {/* Peak temp */}
      <td className="py-2.5 px-3 text-right tabular-nums text-sm font-medium text-accent-critical">
        {exc.peakTempC.toFixed(1)}°C
      </td>

      {/* Duration out of range */}
      <td className="py-2.5 px-3 text-right tabular-nums text-sm text-text-primary">
        {dur}
      </td>

      {/* Degree-minutes */}
      <td className="py-2.5 px-3 text-right tabular-nums text-sm text-text-primary">
        {exc.degreeMinutes}
      </td>

      {/* MKT */}
      <td className="py-2.5 px-3 text-right tabular-nums text-sm text-text-muted">
        {exc.meanKineticTempC.toFixed(1)}°C
      </td>

      {/* Regulatory basis */}
      <td className="py-2.5 px-3 max-w-[220px]">
        <span className="text-[10px] text-text-muted leading-snug font-mono-sensor block truncate" title={exc.regulatoryBasis}>
          {exc.regulatoryBasis}
        </span>
      </td>

      {/* Actionable before delivery */}
      <td className="py-2.5 px-3 text-sm">
        {exc.detectedBeforeDelivery ? (
          <span className="text-xs font-medium text-accent-tracking">Before delivery</span>
        ) : (
          <span className="text-xs text-text-muted">At delivery</span>
        )}
      </td>

      {/* Disposition */}
      <td className="py-2.5 px-3 text-sm">
        <span className={`text-xs font-medium ${DISPOSITION_STYLE[exc.disposition] ?? 'text-text-muted'}`}>
          {DISPOSITION_LABEL[exc.disposition] ?? exc.disposition}
        </span>
      </td>
    </tr>
  );
}

export function ColdChainMonitor() {
  const excursions = useExcursions();
  const shipments = useShipments();
  const location = useLocation();

  // Hash-based highlighting — the shipment detail page links here with #excursion-id
  const highlightedId = location.hash.replace('#', '');

  const rows: ExcursionRow[] = sortRows(
    (excursions.data ?? []).map((e) => ({
      excursion: e,
      shipment: shipments.data?.find((s) => s.id === e.shipmentId),
    })),
  );

  const openCriticalCount = rows.filter(
    (r) => r.excursion.endedAt === null && r.excursion.severity === 'critical',
  ).length;

  const captionId = useId();

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Page header */}
      <div className="flex items-start justify-between mb-5 flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-medium text-text-primary">Cold chain monitor</h1>
          <p className="text-sm text-text-muted mt-0.5">
            Ranked: open critical first, then by severity, then by actionability before delivery.
          </p>
        </div>

        {/* Live counter — aria-live so screen reader announces new breaches */}
        <div
          role="status"
          aria-live="assertive"
          aria-atomic="true"
          aria-label={
            openCriticalCount > 0
              ? `${openCriticalCount} open critical temperature breach${openCriticalCount > 1 ? 'es' : ''}`
              : 'No open critical breaches'
          }
        >
          {openCriticalCount > 0 && (
            <div className="px-4 py-2.5 rounded border border-accent-critical/45 bg-accent-critical/10 flex items-center gap-3">
              <OpenBreachDot />
              <span>
                <span className="text-accent-critical font-medium text-sm">
                  {openCriticalCount} open critical breach{openCriticalCount > 1 ? 'es' : ''}
                </span>
                <span className="text-text-muted text-sm ml-2">— actionable before delivery</span>
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Summary cards for open breaches */}
      {rows.filter(r => r.excursion.endedAt === null).length > 0 && (
        <div className="mb-5 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {rows
            .filter(r => r.excursion.endedAt === null)
            .map(({ excursion: exc, shipment: ship }) => {
              const h = Math.floor(exc.minutesOutOfRange / 60);
              const m = exc.minutesOutOfRange % 60;
              const dur = h > 0 ? `${h}h ${m}m` : `${m}m`;
              const isCritical = exc.severity === 'critical';
              return (
                <div
                  key={exc.id}
                  id={`card-${exc.id}`}
                  className={`p-4 rounded border ${
                    isCritical
                      ? 'border-accent-critical/50 bg-accent-critical/8'
                      : 'border-accent-disruption/40 bg-accent-disruption/5'
                  }`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <SeverityBadge severity={exc.severity} />
                    <span className="text-xs text-text-muted">
                      {format(new Date(exc.startedAt), 'dd MMM HH:mm')} UTC
                    </span>
                  </div>
                  <div className="text-sm font-medium text-text-primary">
                    {ship?.reference ?? exc.shipmentId}
                  </div>
                  <div className="text-xs text-text-muted mt-0.5">
                    {ship?.cargo.description ?? 'Unknown cargo'}
                    {ship && (
                      <span className="ml-1.5 text-text-muted tabular-nums">
                        · ${(ship.cargo.valueUsd / 1000).toFixed(0)}K
                      </span>
                    )}
                  </div>
                  <div className="mt-2 grid grid-cols-3 gap-2 text-xs">
                    <div>
                      <div className="text-text-muted">Peak</div>
                      <div className="tabular-nums font-medium text-accent-critical">
                        {exc.peakTempC.toFixed(1)}°C
                      </div>
                    </div>
                    <div>
                      <div className="text-text-muted">Duration</div>
                      <div className="tabular-nums font-medium text-text-primary">{dur}</div>
                    </div>
                    <div>
                      <div className="text-text-muted">Deg-min</div>
                      <div className="tabular-nums font-medium text-text-primary">
                        {exc.degreeMinutes}
                      </div>
                    </div>
                  </div>
                  <div className="mt-2 text-[10px] text-text-muted font-mono-sensor leading-snug">
                    {exc.regulatoryBasis}
                  </div>
                  <div className="mt-2 flex items-center justify-between">
                    <span className={`text-xs font-medium ${DISPOSITION_STYLE[exc.disposition] ?? 'text-text-muted'}`}>
                      {DISPOSITION_LABEL[exc.disposition] ?? exc.disposition}
                    </span>
                    {ship && (
                      <Link
                        to={`/shipments/${ship.id}`}
                        className="text-xs text-accent-minor hover:underline focus-visible:underline outline-none"
                      >
                        View shipment →
                      </Link>
                    )}
                  </div>
                </div>
              );
            })}
        </div>
      )}

      {/* Full table */}
      <div className="bg-surface-raised rounded border border-surface-border overflow-hidden">
        <AsyncBoundary
          data={rows}
          isLoading={excursions.isLoading || shipments.isLoading}
          isError={excursions.isError}
          error={excursions.error as Error}
          onRetry={() => excursions.refetch()}
          isEmpty={(d) => d.length === 0}
          isStale={excursions.isStale}
          dataUpdatedAt={excursions.dataUpdatedAt}
          loadingFallback={<SkeletonTable rows={5} />}
          emptyFallback={
            <div className="p-10 text-center">
              <p className="text-text-muted text-sm">
                No temperature excursions on record.
              </p>
              <p className="text-text-muted text-xs mt-1">
                All cold chain shipments are within their allowed temperature ranges.
              </p>
            </div>
          }
        >
          {(data) => (
            <div className="overflow-x-auto">
              <table
                className="w-full text-sm border-collapse"
                aria-labelledby={captionId}
              >
                <caption id={captionId} className="sr-only">
                  Cold chain temperature excursions, ranked by severity and actionability
                </caption>
                <thead className="sticky top-0 bg-surface-base border-b border-surface-border z-10">
                  <tr>
                    {[
                      { key: 'shipment', label: 'Shipment', align: 'left' },
                      { key: 'value', label: 'Cargo value', align: 'right' },
                      { key: 'status', label: 'Status', align: 'left' },
                      { key: 'severity', label: 'Severity', align: 'left' },
                      { key: 'peak', label: 'Peak temp', align: 'right' },
                      { key: 'duration', label: 'Duration OOR', align: 'right' },
                      { key: 'degmin', label: 'Deg-min', align: 'right' },
                      { key: 'mkt', label: 'MKT', align: 'right' },
                      { key: 'regulatory', label: 'Regulatory basis', align: 'left' },
                      { key: 'actionable', label: 'Actionable', align: 'left' },
                      { key: 'disposition', label: 'Disposition', align: 'left' },
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
                <tbody>
                  {data.map((row) => (
                    <ExcursionTableRow
                      key={row.excursion.id}
                      row={row}
                      isHighlighted={row.excursion.id === highlightedId}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </AsyncBoundary>
      </div>
    </div>
  );
}
