import React, { useState } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { useAllRerouteOptions, useShipments } from '@/lib/queries';
import { AsyncBoundary } from '@/components/ui/AsyncBoundary';
import { SkeletonCard } from '@/components/ui/Skeleton';
import type { RerouteOption } from '@/types/domain';

const CONTINUITY_STYLES: Record<string, string> = {
  maintained: 'text-accent-tracking',
  at_risk: 'text-accent-disruption',
  broken: 'text-accent-critical',
};
const FEASIBILITY_LABEL: Record<string, string> = {
  confirmed: 'Confirmed',
  likely: 'Likely',
  speculative: 'Speculative',
};

function RerouteCard({ opt }: { opt: RerouteOption }) {
  return (
    <div
      className={`p-5 rounded border flex flex-col gap-3
        ${opt.recommended
          ? 'border-accent-tracking/50 bg-accent-tracking/5'
          : opt.coldChainContinuity === 'broken'
          ? 'border-accent-critical/30 bg-accent-critical/5'
          : 'border-surface-border bg-surface-raised'}`}
    >
      <div className="flex items-start gap-2">
        {opt.recommended && (
          <span className="text-xs font-medium text-accent-tracking shrink-0">★ Recommended</span>
        )}
        <h3 className="text-sm font-medium text-text-primary">{opt.summary}</h3>
      </div>

      {/* Key numbers */}
      <div className="grid grid-cols-3 gap-2 text-sm">
        {[
          {
            label: 'Time delta',
            value: `${opt.deltaDays > 0 ? '+' : ''}${opt.deltaDays}d`,
            cls: opt.deltaDays > 0 ? 'text-accent-disruption' : 'text-accent-tracking',
          },
          {
            label: 'Cost delta',
            value: `${opt.deltaCostUsd > 0 ? '+' : ''}$${Math.abs(opt.deltaCostUsd / 1000).toFixed(0)}K`,
            cls: opt.deltaCostUsd > 0 ? 'text-accent-disruption' : 'text-accent-tracking',
          },
          {
            label: 'CO₂ delta',
            value: `${opt.co2DeltaKg > 0 ? '+' : ''}${opt.co2DeltaKg}kg`,
            cls: opt.co2DeltaKg > 0 ? 'text-text-muted' : 'text-accent-tracking',
          },
        ].map(({ label, value, cls }) => (
          <div key={label} className="bg-surface-base rounded p-2">
            <div className="text-xs text-text-muted mb-0.5">{label}</div>
            <div className={`tabular-nums font-medium ${cls}`}>{value}</div>
          </div>
        ))}
      </div>

      {/* Cold chain */}
      <div className="flex items-center gap-2 text-xs">
        <span className="text-text-muted">Cold chain:</span>
        <span className={CONTINUITY_STYLES[opt.coldChainContinuity] ?? 'text-text-muted'}>
          {opt.coldChainContinuity.replace('_', ' ')}
        </span>
        {opt.coldChainContinuityReason && (
          <span className="text-text-muted">— {opt.coldChainContinuityReason}</span>
        )}
      </div>

      {/* Feasibility */}
      <div className="flex items-center gap-2 text-xs">
        <span className="text-text-muted">Feasibility:</span>
        <span className="text-text-primary">{FEASIBILITY_LABEL[opt.feasibility]}</span>
      </div>

      {/* Rationale — always visible */}
      <p className="text-xs text-text-muted border-t border-surface-border pt-2">
        <span className="text-text-primary font-medium">Why: </span>
        {opt.rationale}
      </p>

      {/* Constraints */}
      {opt.constraints.length > 0 && (
        <ul className="text-xs text-accent-disruption space-y-0.5">
          {opt.constraints.map((c, i) => (
            <li key={i}>⚠ {c}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function RerouteWorkbench() {
  const [params] = useSearchParams();
  const shipmentIdParam = params.get('shipmentId') ?? '';
  const allReroutes = useAllRerouteOptions();
  const shipments = useShipments();
  const [selectedShipmentId, setSelectedShipmentId] = useState(shipmentIdParam);

  const filtered = allReroutes.data?.filter(
    (r) => !selectedShipmentId || r.shipmentId === selectedShipmentId
  ) ?? [];

  const shipmentOptions = shipments.data?.filter(
    (s) => allReroutes.data?.some((r) => r.shipmentId === s.id)
  ) ?? [];

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="mb-6">
        <h1 className="text-xl font-medium text-text-primary">Reroute workbench</h1>
        <p className="text-sm text-text-muted mt-1">
          Compare options side-by-side. The recommended option states its reasoning. "Accept the delay" is always listed.
        </p>
      </div>

      {/* Shipment selector */}
      <div className="mb-4">
        <label htmlFor="shipment-select" className="text-xs text-text-muted block mb-1">
          Shipment
        </label>
        <select
          id="shipment-select"
          value={selectedShipmentId}
          onChange={(e) => setSelectedShipmentId(e.target.value)}
          className="bg-surface-raised border border-surface-border text-text-primary text-sm rounded px-3 py-1.5 outline-none
            focus-visible:ring-2 focus-visible:ring-accent-minor"
        >
          <option value="">All shipments with reroute options</option>
          {shipmentOptions.map((s) => (
            <option key={s.id} value={s.id}>
              {s.reference} — {s.cargo.description}
            </option>
          ))}
        </select>
      </div>

      <AsyncBoundary
        data={filtered}
        isLoading={allReroutes.isLoading}
        isError={allReroutes.isError}
        error={allReroutes.error as Error}
        onRetry={() => allReroutes.refetch()}
        isEmpty={(d) => d.length === 0}
        loadingFallback={
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {[1, 2, 3].map((i) => <SkeletonCard key={i} />)}
          </div>
        }
        emptyFallback={
          <div className="p-8 text-center text-text-muted text-sm">
            No reroute options available. Select a different shipment or check back when options are generated.
          </div>
        }
      >
        {(options) => (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {options.map((opt) => <RerouteCard key={opt.id} opt={opt} />)}
          </div>
        )}
      </AsyncBoundary>
    </div>
  );
}
