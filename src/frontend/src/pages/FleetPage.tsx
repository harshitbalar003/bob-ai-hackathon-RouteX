import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { formatDistanceToNow, format } from 'date-fns';
import { useFleetAssets, useRedeploymentMatches, useShipments } from '@/lib/queries';
import { AsyncBoundary } from '@/components/ui/AsyncBoundary';
import { SkeletonTable } from '@/components/ui/Skeleton';
import { rankIdleAssets, idleCapacityScore } from '@/lib/utils/idleRanking';
import type { FleetAsset, RedeploymentMatch } from '@/types/domain';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
  ReferenceLine,
} from 'recharts';

const TYPE_LABEL: Record<string, string> = {
  truck: 'Truck',
  trailer: 'Trailer',
  container: 'Container',
  reefer_container: 'Reefer container',
  vessel: 'Vessel',
};

const STATUS_STYLES: Record<string, string> = {
  idle: 'text-accent-disruption',
  in_transit: 'text-accent-tracking',
  maintenance: 'text-text-muted',
  reserved: 'text-accent-minor',
};

/** Inline bar showing % utilisation — colour coded */
function UtilBar({ pct }: { pct: number }) {
  const colour = pct < 40 ? '#e8a03a' : pct < 65 ? '#5b9cf6' : '#3ab8c8';
  return (
    <div className="flex items-center gap-2" aria-label={`${pct}% utilisation`}>
      <div className="flex-1 h-1.5 bg-surface-border rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-200"
          style={{ width: `${pct}%`, backgroundColor: colour }}
        />
      </div>
      <span className={`tabular-nums text-xs w-8 text-right ${pct < 40 ? 'text-accent-disruption' : 'text-text-primary'}`}>
        {pct}%
      </span>
    </div>
  );
}

/** Expanded match panel shown inline below the asset row */
function MatchDetail({
  match,
  shipmentRef,
}: {
  match: RedeploymentMatch;
  shipmentRef: string | undefined;
}) {
  return (
    <div className="ml-8 mb-2 mr-4 p-3 rounded border border-accent-tracking/25 bg-accent-tracking/5 text-xs">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="space-y-1">
          <div className="flex items-center gap-3">
            <span className="text-text-muted">Shipment</span>
            <Link
              to={`/tower/shipments/${match.shipmentId}`}
              className="text-accent-minor hover:underline focus-visible:underline outline-none font-medium"
            >
              {shipmentRef ?? match.shipmentId}
            </Link>
          </div>
          <div className="flex items-center gap-6">
            <span>
              <span className="text-text-muted">Distance: </span>
              <span className="tabular-nums text-text-primary">{match.distanceKm} km</span>
            </span>
            <span>
              <span className="text-text-muted">Position time: </span>
              <span className="tabular-nums text-text-primary">{match.hoursToPosition}h</span>
            </span>
            <span>
              <span className="text-text-muted">Utilisation gain: </span>
              <span className="tabular-nums text-accent-tracking font-medium">+{match.utilisationGainPct}%</span>
            </span>
          </div>
          <p className="text-text-muted leading-snug mt-1">{match.rationale}</p>
        </div>
        <div className="text-[10px] text-text-muted shrink-0">
          Generated {formatDistanceToNow(new Date(match.generatedAt), { addSuffix: true })}
        </div>
      </div>
    </div>
  );
}

export function FleetPage() {
  const fleet = useFleetAssets();
  const matches = useRedeploymentMatches();
  const shipments = useShipments();
  const [reeferOnly, setReeferOnly] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const ranked = fleet.data ? rankIdleAssets(fleet.data) : [];
  const filtered = reeferOnly ? ranked.filter((a) => a.reeferCapable) : ranked;

  // All-fleet summary stats
  const totalAssets = fleet.data?.length ?? 0;
  const idleCount = fleet.data?.filter((a) => a.status === 'idle').length ?? 0;
  const avgUtil = fleet.data?.length
    ? Math.round(fleet.data.reduce((s, a) => s + a.utilisationPct30d, 0) / fleet.data.length)
    : 0;
  const reeferIdleCount = fleet.data?.filter((a) => a.status === 'idle' && a.reeferCapable).length ?? 0;

  // Utilisation bar chart data
  const utilizationData = fleet.data
    ? Object.entries(
        fleet.data.reduce<Record<string, { total: number; count: number }>>((acc, a) => {
          if (!acc[a.type]) acc[a.type] = { total: 0, count: 0 };
          acc[a.type].total += a.utilisationPct30d;
          acc[a.type].count += 1;
          return acc;
        }, {}),
      ).map(([type, { total, count }]) => ({
        type: TYPE_LABEL[type] ?? type,
        avg: Math.round(total / count),
      }))
    : [];

  return (
    <div className="p-6 max-w-7xl mx-auto">

      {/* ── Page header ────────────────────────────────────────────── */}
      <div className="mb-5">
        <h1 className="text-xl font-medium text-text-primary">Fleet utilisation</h1>
        <p className="text-sm text-text-muted mt-0.5">
          Idle assets ranked by wasted capacity-hours (idle time × capacity).
        </p>
      </div>

      {/* ── Summary strip ──────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
        {[
          { label: 'Total assets', value: String(totalAssets) },
          { label: 'Idle now', value: String(idleCount), highlight: idleCount > 0 },
          { label: 'Avg 30d utilisation', value: `${avgUtil}%`, highlight: avgUtil < 55 },
          { label: 'Idle reefer units', value: String(reeferIdleCount), highlight: reeferIdleCount > 0 },
        ].map(({ label, value, highlight }) => (
          <div
            key={label}
            className="bg-surface-raised rounded border border-surface-border p-3"
          >
            <div className="text-xs text-text-muted mb-1">{label}</div>
            <div className={`text-lg tabular-nums font-medium ${highlight ? 'text-accent-disruption' : 'text-text-primary'}`}>
              {value}
            </div>
          </div>
        ))}
      </div>

      {/* ── Utilisation chart ──────────────────────────────────────── */}
      <div className="bg-surface-raised rounded border border-surface-border p-4 mb-5">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-medium text-text-primary">
            30-day average utilisation by asset type
          </h2>
          <span className="text-xs text-text-muted">
            Dashed line = 40% threshold (under-utilised below)
          </span>
        </div>
        <AsyncBoundary
          data={utilizationData}
          isLoading={fleet.isLoading}
          isError={fleet.isError}
          isEmpty={(d) => d.length === 0}
          loadingFallback={<div className="h-36 animate-pulse bg-surface-border/20 rounded" />}
          emptyFallback={null}
        >
          {(data) => (
            <ResponsiveContainer width="100%" height={160}>
              <BarChart data={data} margin={{ top: 8, right: 8, bottom: 4, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#263350" vertical={false} />
                <XAxis
                  dataKey="type"
                  tick={{ fill: '#7e94b4', fontSize: 10 }}
                  axisLine={{ stroke: '#263350' }}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fill: '#7e94b4', fontSize: 10 }}
                  tickFormatter={(v: number) => `${v}%`}
                  domain={[0, 100]}
                  axisLine={false}
                  tickLine={false}
                  width={36}
                />
                {/* Under-utilised threshold */}
                <ReferenceLine
                  y={40}
                  stroke="#e8a03a"
                  strokeDasharray="4 3"
                  strokeOpacity={0.6}
                  label={{ value: '40%', position: 'insideTopRight', fill: '#e8a03a', fontSize: 9 }}
                />
                <Tooltip
                  contentStyle={{
                    background: '#162032',
                    border: '1px solid #263350',
                    color: '#e8edf5',
                    fontSize: 12,
                  }}
                  formatter={(v: unknown) => [`${v}%`, '30d avg utilisation']}
                />
                <Bar
                  dataKey="avg"
                  fill="#3ab8c8"
                  radius={[2, 2, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          )}
        </AsyncBoundary>
      </div>

      {/* ── Filter ─────────────────────────────────────────────────── */}
      <div className="flex items-center gap-4 mb-4 flex-wrap">
        <label className="flex items-center gap-2 text-sm text-text-muted cursor-pointer">
          <input
            type="checkbox"
            checked={reeferOnly}
            onChange={(e) => setReeferOnly(e.target.checked)}
            className="rounded accent-accent-tracking"
          />
          ❄ Reefer capable only
        </label>
        <span className="text-xs text-text-muted">
          {filtered.length} idle asset{filtered.length !== 1 ? 's' : ''}
          {reeferOnly ? ' (reefer)' : ''}
        </span>
        {matches.data && matches.data.length > 0 && (
          <span className="text-xs text-text-muted ml-auto">
            {matches.data.length} redeployment match{matches.data.length !== 1 ? 'es' : ''} available
          </span>
        )}
      </div>

      {/* ── Idle assets table ──────────────────────────────────────── */}
      <div className="bg-surface-raised rounded border border-surface-border overflow-hidden">
        <AsyncBoundary
          data={filtered}
          isLoading={fleet.isLoading}
          isError={fleet.isError}
          error={fleet.error as Error}
          onRetry={() => fleet.refetch()}
          isEmpty={(d) => d.length === 0}
          isStale={fleet.isStale}
          dataUpdatedAt={fleet.dataUpdatedAt}
          loadingFallback={<SkeletonTable rows={8} />}
          emptyFallback={
            <div className="p-10 text-center text-text-muted text-sm">
              {reeferOnly
                ? 'No idle reefer assets. Remove the filter to see all idle assets.'
                : 'No idle assets at this time.'}
            </div>
          }
        >
          {(assets) => (
            <div className="overflow-x-auto">
              <table className="w-full text-sm border-collapse">
                <caption className="sr-only">
                  Idle fleet assets ranked by wasted capacity-hours
                </caption>
                <thead className="sticky top-0 bg-surface-base border-b border-surface-border z-10">
                  <tr>
                    {[
                      { key: 'expand', label: '', width: 'w-6' },
                      { key: 'id', label: 'Asset ID', align: 'left' },
                      { key: 'type', label: 'Type', align: 'left' },
                      { key: 'location', label: 'Location', align: 'left' },
                      { key: 'idle', label: 'Idle since', align: 'left' },
                      { key: 'capacity', label: 'Capacity', align: 'right' },
                      { key: 'score', label: 'Idle score ↓', align: 'right' },
                      { key: 'util', label: '30d utilisation', align: 'left', width: 'w-36' },
                      { key: 'match', label: 'Best match', align: 'left' },
                    ].map(({ key, label, align, width }) => (
                      <th
                        key={key}
                        scope="col"
                        className={`py-2 px-3 text-xs font-medium text-text-muted
                          ${align === 'right' ? 'text-right' : 'text-left'}
                          ${width ?? ''}`}
                      >
                        {label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {assets.map((asset) => {
                    const match = matches.data?.find((m) => m.assetId === asset.id);
                    const isExpanded = expandedId === asset.id;
                    const shipmentRef = shipments.data?.find(
                      (s) => s.id === match?.shipmentId,
                    )?.reference;
                    const score = Math.round(idleCapacityScore(asset));

                    return (
                      <React.Fragment key={asset.id}>
                        <tr
                          id={asset.id}
                          className={`border-b border-surface-border hover:bg-surface-raised/40 transition-colors duration-75
                            ${isExpanded ? 'bg-surface-raised/60' : ''}`}
                        >
                          {/* Expand toggle */}
                          <td className="py-2.5 px-3">
                            {match && (
                              <button
                                onClick={() => setExpandedId(isExpanded ? null : asset.id)}
                                aria-expanded={isExpanded}
                                aria-label={`${isExpanded ? 'Collapse' : 'Expand'} redeployment match for ${asset.id}`}
                                className="text-text-muted hover:text-text-primary transition-colors text-xs outline-none focus-visible:ring-2 focus-visible:ring-accent-minor rounded"
                              >
                                {isExpanded ? '▾' : '▸'}
                              </button>
                            )}
                          </td>

                          {/* Asset ID */}
                          <td className="py-2.5 px-3">
                            <span className="font-mono-sensor text-xs text-text-primary">
                              {asset.id}
                            </span>
                          </td>

                          {/* Type */}
                          <td className="py-2.5 px-3 text-text-muted">
                            {TYPE_LABEL[asset.type]}
                            {asset.reeferCapable && (
                              <span className="ml-1.5 text-accent-tracking text-[10px]">❄</span>
                            )}
                          </td>

                          {/* Location */}
                          <td className="py-2.5 px-3 text-text-muted text-xs">
                            {asset.location.label}
                          </td>

                          {/* Idle since */}
                          <td className="py-2.5 px-3">
                            <div className="text-sm tabular-nums text-text-primary">
                              {asset.idleSinceHours}h
                            </div>
                            <div className="text-[10px] text-text-muted font-mono-sensor">
                              since {format(new Date(asset.idleSinceAt), 'dd MMM HH:mm')} UTC
                            </div>
                          </td>

                          {/* Capacity */}
                          <td className="py-2.5 px-3 text-right tabular-nums text-sm">
                            {asset.capacity.value} {asset.capacity.unit}
                          </td>

                          {/* Idle score */}
                          <td className="py-2.5 px-3 text-right">
                            <span
                              className={`tabular-nums text-sm font-medium ${
                                score > 500 ? 'text-accent-disruption' : 'text-text-muted'
                              }`}
                              title="idle hours × normalised capacity"
                            >
                              {score.toLocaleString()}
                            </span>
                          </td>

                          {/* Utilisation bar */}
                          <td className="py-2.5 px-3 w-36">
                            <UtilBar pct={asset.utilisationPct30d} />
                          </td>

                          {/* Best redeployment match */}
                          <td className="py-2.5 px-3">
                            {match ? (
                              <button
                                onClick={() => setExpandedId(isExpanded ? null : asset.id)}
                                className="text-left text-xs text-accent-tracking hover:text-accent-tracking/80 outline-none focus-visible:underline"
                              >
                                → {shipmentRef ?? match.shipmentId}
                                <span className="text-text-muted ml-1.5">
                                  +{match.utilisationGainPct}% · {match.hoursToPosition}h
                                </span>
                              </button>
                            ) : (
                              <span className="text-xs text-text-muted">No match</span>
                            )}
                          </td>
                        </tr>

                        {/* Expanded match detail */}
                        {isExpanded && match && (
                          <tr className="border-b border-surface-border bg-surface-base/60">
                            <td colSpan={9} className="py-0">
                              <MatchDetail
                                match={match}
                                shipmentRef={shipmentRef}
                              />
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </AsyncBoundary>
      </div>
    </div>
  );
}
