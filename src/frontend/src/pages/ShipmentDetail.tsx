import React from 'react';
import { useParams, Link } from 'react-router-dom';
import { format, formatDistanceToNow, differenceInHours } from 'date-fns';
import {
  useShipment,
  useRerouteOptions,
  useSensorReadings,
  useSensorGaps,
  useExcursions,
  useDisruptions,
} from '@/lib/queries';
import { AsyncBoundary } from '@/components/ui/AsyncBoundary';
import { SkeletonCard, SkeletonTable } from '@/components/ui/Skeleton';
import { StatusBadge } from '@/components/ui/Badge';
import { LegTimeline } from '@/components/shipment/LegTimeline';
import { TemperatureTrace } from '@/components/shipment/TemperatureTrace';
import { formatSeverityLine } from '@/lib/utils/severity';
import { Button } from '@/components/ui/Button';
import type { Shipment } from '@/types/domain';
import { useNavigate } from 'react-router-dom';

function EtaDelta({ s }: { s: Shipment }) {
  const hours = differenceInHours(
    new Date(s.etaProjected),
    new Date(s.etaOriginal),
  );
  if (hours === 0) return null;
  return (
    <span className={`text-xs tabular-nums ${hours > 0 ? 'text-accent-disruption' : 'text-accent-tracking'}`}>
      {hours > 0 ? '+' : ''}{hours}h vs original
    </span>
  );
}

export function ShipmentDetail() {
  const { id } = useParams<{ id: string }>();
  const shipment = useShipment(id!);
  const reroutes = useRerouteOptions(id!);
  const sensorReadings = useSensorReadings(id!);
  const sensorGaps = useSensorGaps(id!);
  const allExcursions = useExcursions();
  const allDisruptions = useDisruptions();
  const navigate = useNavigate();

  const shipmentExcursions = allExcursions.data?.filter((e) => e.shipmentId === id) ?? [];
  const openCritical = shipmentExcursions.filter(
    (e) => e.endedAt === null && e.severity === 'critical',
  );
  const blockedLeg = shipment.data?.legs.find((l) => l.status === 'blocked');

  // Disruptions that affect this shipment
  const relatedDisruptions = allDisruptions.data?.filter(
    (d) => shipment.data?.impactedBy.includes(d.id),
  ) ?? [];

  return (
    <div className="p-6 max-w-6xl mx-auto">
      {/* ── Open critical breach banner ──────────────────────────────── */}
      {openCritical.length > 0 && (
        <div
          className="mb-5 px-4 py-3 rounded border border-accent-critical/50 bg-accent-critical/10 flex items-start gap-3"
          role="alert"
        >
          <span className="text-accent-critical text-base shrink-0">◆</span>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-accent-critical">
              Open critical temperature breach — actionable before delivery
            </p>
            {openCritical.map((exc) => (
              <p key={exc.id} className="text-xs text-text-muted mt-0.5">
                {formatSeverityLine(exc)} · {exc.regulatoryBasis}
              </p>
            ))}
          </div>
          <Button
            variant="danger"
            size="sm"
            onClick={() => navigate(`/tower/cold-chain#${openCritical[0].id}`)}
          >
            Review disposition
          </Button>
        </div>
      )}

      <AsyncBoundary
        data={shipment.data}
        isLoading={shipment.isLoading}
        isError={shipment.isError}
        error={shipment.error as Error}
        onRetry={() => shipment.refetch()}
        loadingFallback={<SkeletonCard />}
        emptyFallback={
          <div className="text-text-muted text-sm">
            Shipment not found.{' '}
            <Link to="/tower" className="text-accent-minor underline">
              Return to control tower
            </Link>
          </div>
        }
      >
        {(s) => (
          <div className="space-y-5">
            {/* ── Header ───────────────────────────────────────────────── */}
            <div className="flex items-start justify-between gap-4 flex-wrap">
              <div>
                <div className="flex items-center gap-2 mb-1 flex-wrap">
                  <StatusBadge
                    label={s.status.replace('_', ' ')}
                    variant={s.status as 'on_track' | 'at_risk' | 'delayed' | 'exception' | 'neutral'}
                  />
                  {s.cargo.isColdChain && (
                    <span className="text-xs text-accent-tracking font-medium">❄ Cold chain</span>
                  )}
                  {relatedDisruptions.map((d) => (
                    <Link
                      key={d.id}
                      to={`/tower/disruptions/${d.id}`}
                      className="text-xs text-accent-disruption hover:underline focus-visible:underline outline-none"
                    >
                      ⚠ {d.headline}
                    </Link>
                  ))}
                </div>
                <h1 className="text-xl font-medium text-text-primary">{s.reference}</h1>
                <p className="text-sm text-text-muted mt-0.5">
                  {s.shipper} → {s.consignee}
                </p>
              </div>
              <div className="text-right shrink-0">
                <div className="text-xs text-text-muted mb-0.5">Projected ETA</div>
                <div className="text-lg tabular-nums font-medium text-text-primary leading-tight">
                  {format(new Date(s.etaProjected), 'dd MMM HH:mm')} UTC
                </div>
                <div className="flex items-center gap-2 justify-end mt-0.5">
                  <span className="text-xs text-text-muted tabular-nums">
                    Original: {format(new Date(s.etaOriginal), 'dd MMM HH:mm')} UTC
                  </span>
                  <EtaDelta s={s} />
                </div>
              </div>
            </div>

            {/* ── Leg timeline ─────────────────────────────────────────── */}
            <section aria-labelledby="timeline-heading">
              <div className="bg-surface-raised rounded border border-surface-border p-4">
                <h2
                  id="timeline-heading"
                  className="text-sm font-medium text-text-primary mb-3"
                >
                  Journey timeline
                </h2>
                <LegTimeline
                  legs={s.legs}
                  blockedLegId={blockedLeg?.id}
                  disruptions={relatedDisruptions}
                />
              </div>
            </section>

            {/* ── Cargo + Route ─────────────────────────────────────────── */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <section
                aria-labelledby="cargo-heading"
                className="bg-surface-raised rounded border border-surface-border p-4"
              >
                <h2 id="cargo-heading" className="text-sm font-medium text-text-primary mb-3">
                  Cargo
                </h2>
                <dl className="space-y-2">
                  {[
                    { label: 'Description', value: s.cargo.description },
                    {
                      label: 'Value',
                      value: (
                        <span className="tabular-nums">
                          ${(s.cargo.valueUsd / 1000).toFixed(0)}K
                        </span>
                      ),
                    },
                    ...(s.cargo.isColdChain && s.cargo.tempRangeC
                      ? [
                          {
                            label: 'Temperature range',
                            value: (
                              <span className="tabular-nums text-accent-tracking">
                                {s.cargo.tempRangeC.min}°C – {s.cargo.tempRangeC.max}°C
                              </span>
                            ),
                          },
                          {
                            label: 'Regulatory regime',
                            value: s.cargo.regulatoryRegime ?? '—',
                          },
                        ]
                      : []),
                    {
                      label: 'Risk score',
                      value: (
                        <span
                          className={`tabular-nums font-medium ${
                            s.riskScore >= 75
                              ? 'text-accent-critical'
                              : s.riskScore >= 40
                              ? 'text-accent-disruption'
                              : 'text-text-primary'
                          }`}
                        >
                          {s.riskScore} / 100
                        </span>
                      ),
                    },
                  ].map(({ label, value }) => (
                    <div key={label} className="flex justify-between items-baseline gap-4">
                      <dt className="text-xs text-text-muted shrink-0">{label}</dt>
                      <dd className="text-sm text-text-primary text-right">{value}</dd>
                    </div>
                  ))}
                </dl>
              </section>

              <section
                aria-labelledby="route-heading"
                className="bg-surface-raised rounded border border-surface-border p-4"
              >
                <h2 id="route-heading" className="text-sm font-medium text-text-primary mb-3">
                  Route
                </h2>
                <dl className="space-y-2">
                  {[
                    { label: 'Shipper', value: s.shipper },
                    { label: 'Consignee', value: s.consignee },
                    { label: 'Origin', value: s.origin.label },
                    { label: 'Destination', value: s.destination.label },
                    ...(s.impactedBy.length > 0
                      ? [
                          {
                            label: 'Disruptions',
                            value: (
                              <span className="text-accent-disruption text-xs">
                                {s.impactedBy.length} active
                              </span>
                            ),
                          },
                        ]
                      : []),
                  ].map(({ label, value }) => (
                    <div key={label} className="flex justify-between items-baseline gap-4">
                      <dt className="text-xs text-text-muted shrink-0">{label}</dt>
                      <dd className="text-sm text-text-primary text-right">{value}</dd>
                    </div>
                  ))}
                </dl>
              </section>
            </div>

            {/* ── Temperature trace (cold chain only) ──────────────────── */}
            {s.cargo.isColdChain && s.cargo.tempRangeC && (
              <section aria-labelledby="temp-heading">
                <div className="bg-surface-raised rounded border border-surface-border p-4">
                  <div className="flex items-center justify-between mb-3">
                    <h2
                      id="temp-heading"
                      className="text-sm font-medium text-text-primary"
                    >
                      Temperature trace
                    </h2>
                    <span className="text-xs text-accent-tracking">
                      Allowed: {s.cargo.tempRangeC.min}°C – {s.cargo.tempRangeC.max}°C
                      {s.cargo.regulatoryRegime && (
                        <span className="text-text-muted ml-1">({s.cargo.regulatoryRegime})</span>
                      )}
                    </span>
                  </div>

                  <AsyncBoundary
                    data={sensorReadings.data}
                    isLoading={sensorReadings.isLoading}
                    isError={sensorReadings.isError}
                    error={sensorReadings.error as Error}
                    onRetry={() => sensorReadings.refetch()}
                    isEmpty={(d) => d.length === 0}
                    loadingFallback={
                      <div className="h-52 bg-surface-border/20 animate-pulse rounded" />
                    }
                    emptyFallback={
                      <div className="h-52 flex items-center justify-center text-text-muted text-sm">
                        No sensor data available for this shipment
                      </div>
                    }
                  >
                    {(readings) => (
                      <TemperatureTrace
                        readings={readings}
                        gaps={sensorGaps.data ?? []}
                        excursions={shipmentExcursions}
                        tempRangeC={s.cargo.tempRangeC!}
                      />
                    )}
                  </AsyncBoundary>
                </div>
              </section>
            )}

            {/* ── Reroute options ───────────────────────────────────────── */}
            <section aria-labelledby="reroutes-heading">
              <div className="flex items-center justify-between mb-3">
                <h2
                  id="reroutes-heading"
                  className="text-base font-medium text-text-primary"
                >
                  Reroute options
                </h2>
                <Link
                  to={`/tower/reroutes?shipmentId=${s.id}`}
                  className="text-sm text-accent-minor hover:underline focus-visible:underline outline-none"
                >
                  Open workbench →
                </Link>
              </div>

              <AsyncBoundary
                data={reroutes.data}
                isLoading={reroutes.isLoading}
                isError={reroutes.isError}
                onRetry={() => reroutes.refetch()}
                isEmpty={(d) => d.length === 0}
                loadingFallback={<SkeletonTable rows={3} />}
                emptyFallback={
                  <div className="p-4 rounded border border-surface-border bg-surface-raised text-center text-text-muted text-sm">
                    No reroute options available for this shipment
                  </div>
                }
              >
                {(options) => (
                  <div className="space-y-2">
                    {options.map((opt) => (
                      <div
                        key={opt.id}
                        className={`p-4 rounded border ${
                          opt.recommended
                            ? 'border-accent-tracking/50 bg-accent-tracking/5'
                            : 'border-surface-border bg-surface-raised'
                        }`}
                      >
                        <div className="flex items-start justify-between gap-4 flex-wrap">
                          <div className="min-w-0">
                            {opt.recommended && (
                              <span className="text-xs text-accent-tracking font-medium mr-2">
                                ★ Recommended
                              </span>
                            )}
                            <span className="text-sm font-medium text-text-primary">
                              {opt.summary}
                            </span>
                          </div>
                          <div className="flex gap-4 text-xs tabular-nums shrink-0">
                            <span
                              className={
                                opt.deltaDays > 0 ? 'text-accent-disruption' : 'text-accent-tracking'
                              }
                            >
                              {opt.deltaDays > 0 ? '+' : ''}
                              {opt.deltaDays}d
                            </span>
                            <span
                              className={
                                opt.deltaCostUsd > 0
                                  ? 'text-accent-disruption'
                                  : 'text-accent-tracking'
                              }
                            >
                              {opt.deltaCostUsd > 0 ? '+' : ''}$
                              {Math.abs(opt.deltaCostUsd / 1000).toFixed(0)}K
                            </span>
                          </div>
                        </div>
                        <p className="text-xs text-text-muted mt-1.5 leading-relaxed">
                          {opt.rationale}
                        </p>
                        {opt.constraints.length > 0 && (
                          <ul className="mt-1.5 space-y-0.5">
                            {opt.constraints.map((c) => (
                              <li key={c} className="text-xs text-accent-disruption">
                                ⚠ {c}
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </AsyncBoundary>
            </section>
          </div>
        )}
      </AsyncBoundary>
    </div>
  );
}
