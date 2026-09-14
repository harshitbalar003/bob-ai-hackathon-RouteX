import React from 'react';
import { useDisruptions, useShipments, useFleetAssets, usePriorityQueue } from '@/lib/queries';
import { AsyncBoundary } from '@/components/ui/AsyncBoundary';
import { SkeletonTable } from '@/components/ui/Skeleton';
import { DisruptionBand } from '@/components/control-tower/DisruptionBand';
import { PriorityQueue } from '@/components/control-tower/PriorityQueue';
import { WorldMap } from '@/components/map/WorldMap';
import { useUIStore } from '@/lib/store';

function MapLayerToggle() {
  const { mapLayerRoutes, mapLayerZones, mapLayerAssets, toggleMapLayer } = useUIStore();
  const layers: { key: 'routes' | 'zones' | 'assets'; label: string; active: boolean }[] = [
    { key: 'routes', label: 'Routes', active: mapLayerRoutes },
    { key: 'zones', label: 'Zones', active: mapLayerZones },
    { key: 'assets', label: 'Assets', active: mapLayerAssets },
  ];
  return (
    <div
      className="flex items-center gap-0.5 bg-surface-base/70 backdrop-blur rounded border border-surface-border px-1 py-0.5"
      role="group"
      aria-label="Map layer toggles"
    >
      {layers.map(({ key, label, active }) => (
        <button
          key={key}
          onClick={() => toggleMapLayer(key)}
          aria-pressed={active}
          className={`px-2 py-0.5 rounded text-xs transition-colors duration-75 outline-none
            focus-visible:ring-2 focus-visible:ring-accent-minor
            ${active
              ? 'bg-surface-border text-text-primary'
              : 'text-text-muted hover:text-text-primary'}`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

export function ControlTower() {
  const disruptions = useDisruptions();
  const shipments = useShipments();
  const fleet = useFleetAssets();
  const queue = usePriorityQueue();

  const mapReady = !!(shipments.data && fleet.data);

  return (
    <div className="flex flex-col" style={{ height: 'calc(100vh - 44px)' }}>
      {/* Disruption band */}
      <AsyncBoundary
        data={disruptions.data}
        isLoading={disruptions.isLoading}
        isError={disruptions.isError}
        error={disruptions.error as Error}
        isEmpty={(d) => d.length === 0}
        loadingFallback={
          <div className="h-12 border-b border-surface-border bg-surface-raised/50 animate-pulse" />
        }
        emptyFallback={null}
      >
        {(data) => <DisruptionBand disruptions={data} />}
      </AsyncBoundary>

      {/* Main split: map + priority queue */}
      <div className="flex flex-1 overflow-hidden min-h-0">

        {/* ── Map ─────────────────────────────────────────────── 60% */}
        <div className="relative bg-surface-map overflow-hidden border-r border-surface-border"
          style={{ flex: '0 0 60%' }}>

          {/* Layer toggle overlay */}
          <div className="absolute top-3 right-3 z-10">
            <MapLayerToggle />
          </div>

          {mapReady ? (
            <WorldMap
              shipments={shipments.data!}
              disruptions={disruptions.data ?? []}
              assets={fleet.data!}
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center">
              {(shipments.isError || fleet.isError) ? (
                <div className="text-sm text-accent-critical text-center px-8">
                  <p className="font-medium mb-1">Failed to load map data</p>
                  <button
                    onClick={() => { shipments.refetch(); fleet.refetch(); }}
                    className="text-xs text-text-muted underline hover:text-text-primary"
                  >
                    Retry
                  </button>
                </div>
              ) : (
                <div className="w-3/4 h-1/2 bg-surface-border/15 animate-pulse rounded" />
              )}
            </div>
          )}
        </div>

        {/* ── Priority queue ──────────────────────────────────── 40% */}
        <div className="flex flex-col overflow-hidden" style={{ flex: '0 0 40%' }}>

          {/* Header */}
          <div className="px-4 pt-3 pb-2 border-b border-surface-border shrink-0">
            <h2 className="text-sm font-medium text-text-primary leading-tight">
              Actions needed
            </h2>
            <p className="text-xs text-text-muted mt-0.5">
              Ranked by stake — click any row to open
            </p>
          </div>

          {/* Queue list */}
          <div className="flex-1 overflow-y-auto">
            <AsyncBoundary
              data={queue.data}
              isLoading={queue.isLoading}
              isError={queue.isError}
              error={queue.error as Error}
              isEmpty={(d) => d.length === 0}
              isStale={queue.isStale}
              dataUpdatedAt={queue.dataUpdatedAt}
              onRetry={() => queue.refetch()}
              loadingFallback={<SkeletonTable rows={8} />}
              emptyFallback={
                <div className="flex flex-col items-center justify-center h-40 text-text-muted text-sm gap-1">
                  <span className="text-base text-text-muted">✓</span>
                  <span>No active exceptions</span>
                  <span className="text-xs">All shipments on track</span>
                </div>
              }
            >
              {(items) => <PriorityQueue items={items} />}
            </AsyncBoundary>
          </div>
        </div>

      </div>
    </div>
  );
}
