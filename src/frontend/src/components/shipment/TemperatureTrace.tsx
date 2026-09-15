import React, { useMemo } from 'react';
import {
  ComposedChart, Line, XAxis, YAxis, Tooltip, ReferenceLine, ReferenceArea,
  ResponsiveContainer, CartesianGrid,
} from 'recharts';
import { format } from 'date-fns';
import type { SensorReading, SensorGap, Excursion, Prediction } from '@/types/domain';

interface TemperatureTraceProps {
  readings: SensorReading[];
  gaps: SensorGap[];
  excursions: Excursion[];
  tempRangeC: { min: number; max: number };
  /**
   * Optional ML breach-risk prediction for this shipment.
   * When provided, a dashed forward-projected band is drawn beyond the last
   * real reading. This is VISUALLY DISTINCT from the observed trace — the
   * dashed band must never be mistaken for actual sensor data.
   *
   * The band represents the forecast horizon (4 hours forward from predictedAt).
   * It carries the probability and a "ML forecast — not sensor data" label.
   * No regulatory citation is ever shown here.
   */
  prediction?: Prediction;
}

// A point in the Recharts data array.
// tempC === null signals a gap — Recharts will not draw a line through it
// when connectNulls={false}.
interface DataPoint {
  ts: number;
  tempC: number | null;
  isGap?: boolean;
}

interface GapRegion {
  x1: number;
  x2: number;
  durationMinutes: number;
}

const CustomTooltip = ({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: DataPoint }>;
}) => {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  if (p.tempC === null || p.isGap) return null;
  return (
    <div className="bg-surface-raised border border-surface-border rounded px-2.5 py-1.5 text-xs">
      <div className="text-text-muted font-mono-sensor">
        {format(new Date(p.ts), 'dd MMM HH:mm:ss')} UTC
      </div>
      <div className="text-text-primary tabular-nums font-medium mt-0.5">
        {p.tempC.toFixed(1)}°C
      </div>
    </div>
  );
};

export function TemperatureTrace({
  readings,
  gaps,
  excursions,
  tempRangeC,
  prediction,
}: TemperatureTraceProps) {
  const { data, gapRegions, yDomain } = useMemo(() => {
    if (readings.length === 0) {
      return { data: [], gapRegions: [] as GapRegion[], yDomain: [0, 30] as [number, number] };
    }

    // Sort readings by timestamp
    const sorted = [...readings].sort(
      (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
    );

    // Build gap regions
    const gapRegions: GapRegion[] = gaps.map((g) => ({
      x1: new Date(g.gapStartAt).getTime(),
      x2: new Date(g.gapEndAt).getTime(),
      durationMinutes: g.durationMinutes,
    }));

    // Build data array.
    // At each gap boundary, insert a null point so Recharts breaks the line.
    // Strategy:
    //   1. Convert readings to DataPoints
    //   2. For each gap, find the last reading before the gap and the first after
    //   3. Insert a null sentinel between them
    const points: DataPoint[] = sorted.map((r) => ({
      ts: new Date(r.timestamp).getTime(),
      tempC: r.tempC,
    }));

    // Insert null sentinels for gaps
    const withGaps: DataPoint[] = [];
    for (let i = 0; i < points.length; i++) {
      const pt = points[i];
      // Check if this point falls inside any gap (skip it — we don't want readings
      // that landed inside a declared gap, though in practice there shouldn't be any)
      const insideGap = gapRegions.some((g) => pt.ts > g.x1 && pt.ts < g.x2);
      if (insideGap) continue;

      // Check if we just crossed a gap boundary (previous point was before a gap,
      // this point is after it)
      if (withGaps.length > 0) {
        const prev = withGaps[withGaps.length - 1];
        const gap = gapRegions.find(
          (g) => prev.ts <= g.x1 && pt.ts >= g.x2,
        );
        if (gap) {
          // Insert null sentinel at the gap midpoint so Recharts breaks the line
          withGaps.push({ ts: (gap.x1 + gap.x2) / 2, tempC: null, isGap: true });
        }
      }

      withGaps.push(pt);
    }

    // Y-axis domain: expand beyond allowed range to show breaches clearly
    const temps = points.map((p) => p.tempC ?? 0);
    const dataMin = Math.min(...temps);
    const dataMax = Math.max(...temps);
    const rangeSpan = Math.max(10, tempRangeC.max - tempRangeC.min);
    const yMin = Math.min(dataMin, tempRangeC.min) - rangeSpan * 0.3;
    const yMax = Math.max(dataMax, tempRangeC.max) + rangeSpan * 0.3;

    return {
      data: withGaps,
      gapRegions,
      yDomain: [
        Math.round(yMin * 10) / 10,
        Math.round(yMax * 10) / 10,
      ] as [number, number],
    };
  }, [readings, gaps, tempRangeC]);

  if (data.length === 0) {
    return (
      <div className="flex items-center justify-center h-52 text-text-muted text-sm">
        No sensor data available for this shipment
      </div>
    );
  }

  const openExcursions = excursions.filter((e) => e.endedAt === null);
  const lastTs = data[data.length - 1]?.ts ?? 0;

  // ML forecast band: drawn from lastTs forward to lastTs + horizonHours
  // NEVER drawn over observed data. Visually separated with a distinct colour + dashed stroke.
  const forecastBand = useMemo(() => {
    if (!prediction) return null;
    const horizonMs = prediction.horizonHours * 60 * 60 * 1000;
    return {
      x1: lastTs,
      x2: lastTs + horizonMs,
      probability: prediction.value,
      pct: Math.round(prediction.value * 100),
      isAlert: prediction.value >= 0.5,
    };
  }, [prediction, lastTs]);

  return (
    <div className="space-y-2">
      <ResponsiveContainer width="100%" height={240}>
        <ComposedChart
          data={data}
          margin={{ top: 8, right: 16, bottom: 4, left: 4 }}
        >
          <CartesianGrid
            strokeDasharray="3 3"
            stroke="#263350"
            vertical={false}
          />

          {/* ── Allowed temperature band ───────────────────────────────── */}
          <ReferenceArea
            y1={tempRangeC.min}
            y2={tempRangeC.max}
            fill="#3ab8c8"
            fillOpacity={0.05}
            stroke="none"
          />

          {/* Limit lines */}
          <ReferenceLine
            y={tempRangeC.min}
            stroke="#3ab8c8"
            strokeDasharray="4 3"
            strokeOpacity={0.45}
            label={{
              value: `${tempRangeC.min}°C  `,
              position: 'insideTopLeft',
              fill: '#3ab8c8',
              fontSize: 9,
            }}
          />
          <ReferenceLine
            y={tempRangeC.max}
            stroke="#3ab8c8"
            strokeDasharray="4 3"
            strokeOpacity={0.45}
            label={{
              value: `${tempRangeC.max}°C  `,
              position: 'insideBottomLeft',
              fill: '#3ab8c8',
              fontSize: 9,
            }}
          />

          {/* ── Excursion regions ──────────────────────────────────────── */}
          {excursions.map((exc) => {
            const x2 = exc.endedAt
              ? new Date(exc.endedAt).getTime()
              : lastTs;
            return (
              <ReferenceArea
                key={exc.id}
                x1={new Date(exc.startedAt).getTime()}
                x2={x2}
                fill="#e84040"
                fillOpacity={exc.endedAt === null ? 0.14 : 0.08}
                stroke="#e84040"
                strokeOpacity={0.25}
                strokeWidth={0.5}
              />
            );
          })}

          {/* Open excursion annotation (right edge label) */}
          {openExcursions.map((exc) => (
            <ReferenceLine
              key={`open-${exc.id}`}
              x={lastTs}
              stroke="#e84040"
              strokeDasharray="3 2"
              strokeOpacity={0.6}
              label={{
                value: '⚠ open breach',
                position: 'insideTopRight',
                fill: '#e84040',
                fontSize: 9,
              }}
            />
          ))}

          {/* ── ML Forecast band ──────────────────────────────────────── */}
          {/* VISUALLY DISTINCT from observed trace: hatched, amber/orange  */}
          {/* NO regulatory citation. Shows probability + horizon only.    */}
          {forecastBand && (
            <>
              <ReferenceArea
                x1={forecastBand.x1}
                x2={forecastBand.x2}
                fill={forecastBand.isAlert ? '#e8a03a' : '#7a99b8'}
                fillOpacity={0.08}
                stroke={forecastBand.isAlert ? '#e8a03a' : '#7a99b8'}
                strokeOpacity={0.35}
                strokeWidth={0.5}
                strokeDasharray="4 3"
              />
              <ReferenceLine
                x={forecastBand.x1}
                stroke={forecastBand.isAlert ? '#e8a03a' : '#7a99b8'}
                strokeDasharray="3 2"
                strokeOpacity={0.6}
                strokeWidth={1}
                label={{
                  value: `~ ${forecastBand.pct}% risk (4h forecast)`,
                  position: 'insideTopRight',
                  fill: forecastBand.isAlert ? '#e8a03a' : '#7a99b8',
                  fontSize: 9,
                }}
              />
            </>
          )}

          {/* ── Data gap regions ───────────────────────────────────────── */}
          {gapRegions.map((g, i) => (
            <ReferenceArea
              key={`gap-${i}`}
              x1={g.x1}
              x2={g.x2}
              fill="#1a2840"
              fillOpacity={0.9}
              stroke="#263350"
              strokeOpacity={0.6}
              strokeWidth={0.5}
              label={{
                value: `no data  ${g.durationMinutes}m`,
                position: 'insideTop',
                fill: '#7e94b4',
                fontSize: 8,
              }}
            />
          ))}

          <XAxis
            dataKey="ts"
            type="number"
            scale="time"
            domain={['dataMin', 'dataMax']}
            tickFormatter={(ts: number) => format(new Date(ts), 'HH:mm')}
            tick={{ fill: '#7e94b4', fontSize: 10 }}
            axisLine={{ stroke: '#263350' }}
            tickLine={false}
            minTickGap={40}
          />
          <YAxis
            domain={yDomain}
            tick={{ fill: '#7e94b4', fontSize: 10 }}
            tickFormatter={(v: number) => `${v}°C`}
            axisLine={false}
            tickLine={false}
            width={46}
          />

          <Tooltip
            content={<CustomTooltip />}
            cursor={{ stroke: '#263350', strokeWidth: 1 }}
          />

          {/* Temperature line — connectNulls={false} breaks line at null sentinels */}
          <Line
            dataKey="tempC"
            stroke="#3ab8c8"
            strokeWidth={1.5}
            dot={false}
            connectNulls={false}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>

      {/* Gap annotation below chart */}
      {gapRegions.length > 0 && (
        <div className="flex items-center gap-2 text-xs text-text-muted px-1">
          <span
            className="inline-block w-6 h-3 rounded-sm border border-surface-border bg-[#1a2840]"
            aria-hidden="true"
          />
          <span>
            No sensor reading for{' '}
            {gapRegions.map((g) => `${g.durationMinutes} min`).join(', ')}.{' '}
            Temperature is unknown during this period — do not interpolate.
          </span>
        </div>
      )}

      {/* ML prediction annotation — visually distinct from excursion annotations */}
      {forecastBand && (
        <div className="flex items-start gap-2 px-1 mt-1">
          <span
            className={[
              'inline-block shrink-0 w-3 h-3 rounded-sm border mt-0.5',
              forecastBand.isAlert
                ? 'bg-accent-disruption/10 border-accent-disruption/50'
                : 'bg-text-muted/10 border-text-muted/40',
            ].join(' ')}
            aria-hidden="true"
          />
          <div className="text-xs space-y-0.5">
            <div
              className={
                forecastBand.isAlert
                  ? 'text-accent-disruption font-medium'
                  : 'text-text-muted'
              }
            >
              {forecastBand.isAlert ? 'ALERT' : 'WATCH'} —{' '}
              {forecastBand.pct}% predicted breach risk within{' '}
              {prediction!.horizonHours}h
            </div>
            <div className="text-text-muted">
              ML forecast only — not sensor data. No regulatory citation.
              {prediction!.value < 0.5 && ' Below 50%: low confidence watch signal.'}
            </div>
          </div>
        </div>
      )}

      {/* Excursion annotations below chart */}
      {excursions.length > 0 && (
        <div className="space-y-1 px-1">
          {excursions.map((exc) => {
            const h = Math.floor(exc.minutesOutOfRange / 60);
            const m = exc.minutesOutOfRange % 60;
            const dur = h > 0 ? `${h}h ${m}m` : `${m}m`;
            return (
              <div
                key={exc.id}
                className="flex items-center gap-2 text-xs text-text-muted"
              >
                <span
                  className="inline-block w-3 h-3 rounded-sm bg-accent-critical/20 border border-accent-critical/40 shrink-0"
                  aria-hidden="true"
                />
                <span>
                  <span
                    className={
                      exc.endedAt === null
                        ? 'text-accent-critical font-medium'
                        : 'text-text-muted'
                    }
                  >
                    {exc.endedAt === null ? 'Open' : 'Resolved'} breach
                  </span>{' '}
                  — {exc.peakTempC.toFixed(1)}°C peak · {dur} out of range ·{' '}
                  {exc.degreeMinutes} deg-min ·{' '}
                  <span className="font-mono-sensor">{exc.regulatoryBasis}</span>
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
