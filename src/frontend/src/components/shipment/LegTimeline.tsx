import React, { useMemo } from 'react';
import { format } from 'date-fns';
import type { Leg, Disruption } from '@/types/domain';

interface LegTimelineProps {
  legs: Leg[];
  blockedLegId?: string;
  disruptions?: Disruption[]; // overlaid at the point they intersect
}

const MODE_COLOUR: Record<string, string> = {
  ocean: '#3ab8c8',
  air: '#5b9cf6',
  road: '#7e94b4',
  rail: '#e8a03a',
};

const MODE_LABEL: Record<string, string> = {
  ocean: 'Ocean',
  air: 'Air',
  road: 'Road',
  rail: 'Rail',
};

const STATUS_LABEL: Record<string, string> = {
  completed: 'Completed',
  in_transit: 'In transit',
  scheduled: 'Scheduled',
  blocked: 'Blocked',
};

const SVG_H = 52;      // total SVG height
const BAR_Y = 18;      // top of the bar
const BAR_H = 20;      // bar height
const MARKER_R = 5;    // node circle radius

export function LegTimeline({ legs, blockedLegId, disruptions = [] }: LegTimelineProps) {
  const sorted = useMemo(() => [...legs].sort((a, b) => a.sequence - b.sequence), [legs]);

  const totalMs = useMemo(() =>
    sorted.reduce((sum, l) =>
      sum + (new Date(l.arrivesAt).getTime() - new Date(l.departsAt).getTime()), 0),
    [sorted]);

  const now = Date.now();
  const spanStart = sorted[0] ? new Date(sorted[0].departsAt).getTime() : now;
  const spanEnd = sorted[sorted.length - 1]
    ? new Date(sorted[sorted.length - 1].arrivesAt).getTime()
    : now;
  const spanMs = spanEnd - spanStart || 1;

  // Convert a timestamp to an SVG x% position
  function toX(ts: number): number {
    return Math.max(0, Math.min(100, ((ts - spanStart) / spanMs) * 100));
  }

  const nowX = toX(now);
  const showNow = now > spanStart && now < spanEnd;

  if (sorted.length === 0) return null;

  // Build leg bar data
  const legBars = sorted.map((leg) => {
    const startMs = new Date(leg.departsAt).getTime();
    const endMs = new Date(leg.arrivesAt).getTime();
    const x1 = toX(startMs);
    const x2 = toX(endMs);
    const isBlocked = leg.id === blockedLegId || leg.status === 'blocked';
    const colour = isBlocked ? '#e84040' : (MODE_COLOUR[leg.mode] ?? '#7e94b4');
    const opacity =
      leg.status === 'completed' ? 0.38 :
      leg.status === 'scheduled' ? 0.55 : 1;
    // Progress fill for in-transit legs
    const progressX = leg.status === 'in_transit' && now > startMs
      ? toX(Math.min(now, endMs))
      : null;
    return { leg, x1, x2, colour, opacity, isBlocked, progressX };
  });

  // Node positions (unique departure/arrival timestamps)
  const nodes = useMemo(() => {
    const pts = new Map<number, string>();
    for (const leg of sorted) {
      const t1 = new Date(leg.departsAt).getTime();
      const t2 = new Date(leg.arrivesAt).getTime();
      if (!pts.has(t1)) pts.set(t1, leg.from.label);
      if (!pts.has(t2)) pts.set(t2, leg.to.label);
    }
    return Array.from(pts.entries()).map(([ts, label]) => ({
      x: toX(ts), label, ts,
    }));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sorted, spanStart, spanMs]);

  // Disruption intersection markers — where a disruption's time window overlaps the span
  const disruptionMarkers = disruptions
    .map((dis) => {
      const disStart = new Date(dis.startedAt).getTime();
      const x = toX(disStart);
      if (x < 0 || x > 100) return null;
      return { id: dis.id, x, headline: dis.headline, severity: dis.severity };
    })
    .filter(Boolean);

  return (
    <div className="space-y-1">
      {/* Main SVG timeline */}
      <svg
        viewBox={`0 0 100 ${SVG_H}`}
        preserveAspectRatio="none"
        className="w-full"
        style={{ height: `${SVG_H * 2}px` }}
        role="img"
        aria-label={`Journey timeline: ${sorted.length} leg${sorted.length !== 1 ? 's' : ''}`}
      >
        {/* Track baseline */}
        <line
          x1="0" y1={BAR_Y + BAR_H / 2}
          x2="100" y2={BAR_Y + BAR_H / 2}
          stroke="#263350" strokeWidth="0.5"
        />

        {/* Leg bars */}
        {legBars.map(({ leg, x1, x2, colour, opacity, isBlocked, progressX }) => (
          <g key={leg.id} opacity={opacity}>
            {/* Background bar */}
            <rect
              x={x1} y={BAR_Y}
              width={Math.max(0.5, x2 - x1)} height={BAR_H}
              fill={colour}
              rx="0.4"
            />
            {/* Progress overlay */}
            {progressX !== null && (
              <rect
                x={x1} y={BAR_Y}
                width={Math.max(0, progressX - x1)} height={BAR_H}
                fill="rgba(255,255,255,0.12)"
                rx="0.4"
              />
            )}
            {/* Blocked X marker */}
            {isBlocked && (
              <text
                x={(x1 + x2) / 2} y={BAR_Y + BAR_H / 2 + 1}
                textAnchor="middle" dominantBaseline="middle"
                fill="white" fontSize="5" fontWeight="bold"
              >
                ✕ BLOCKED
              </text>
            )}
            {/* Mode label (only if wide enough) */}
            {!isBlocked && x2 - x1 > 12 && (
              <text
                x={(x1 + x2) / 2} y={BAR_Y + BAR_H / 2 + 1}
                textAnchor="middle" dominantBaseline="middle"
                fill="rgba(255,255,255,0.75)" fontSize="3.5"
              >
                {MODE_LABEL[leg.mode]}
              </text>
            )}
          </g>
        ))}

        {/* Node circles */}
        {nodes.map(({ x, label }) => (
          <g key={`${x}-${label}`}>
            <circle
              cx={x} cy={BAR_Y + BAR_H / 2}
              r={MARKER_R * 0.8}
              fill="#0e1621"
              stroke="#263350"
              strokeWidth="0.7"
            />
            <circle
              cx={x} cy={BAR_Y + BAR_H / 2}
              r={MARKER_R * 0.4}
              fill="#7e94b4"
            />
          </g>
        ))}

        {/* "Now" position marker */}
        {showNow && (
          <g>
            <line
              x1={nowX} y1={BAR_Y - 3}
              x2={nowX} y2={BAR_Y + BAR_H + 3}
              stroke="#e8edf5"
              strokeWidth="0.6"
              strokeDasharray="1.5,1"
            />
            <text
              x={nowX} y={BAR_Y - 5}
              textAnchor="middle"
              fill="#e8edf5"
              fontSize="3.5"
            >
              now
            </text>
          </g>
        )}

        {/* Disruption markers */}
        {disruptionMarkers.map((m) => m && (
          <g key={m.id}>
            <line
              x1={m.x} y1={BAR_Y}
              x2={m.x} y2={BAR_Y + BAR_H}
              stroke="#e8a03a"
              strokeWidth="0.8"
              strokeDasharray="2,1"
            />
            <polygon
              points={`${m.x - 1.5},${BAR_Y} ${m.x + 1.5},${BAR_Y} ${m.x},${BAR_Y - 3}`}
              fill="#e8a03a"
            />
          </g>
        ))}

        {/* Start and end timestamp labels */}
        <text x="0.5" y={SVG_H - 1} fill="#7e94b4" fontSize="3.5">
          {format(new Date(sorted[0].departsAt), 'dd MMM HH:mm')} UTC
        </text>
        <text x="99.5" y={SVG_H - 1} textAnchor="end" fill="#7e94b4" fontSize="3.5">
          {format(new Date(sorted[sorted.length - 1].arrivesAt), 'dd MMM HH:mm')} UTC
        </text>
      </svg>

      {/* Per-leg detail rows */}
      <div className="space-y-0.5 mt-1">
        {sorted.map((leg) => {
          const isBlocked = leg.id === blockedLegId || leg.status === 'blocked';
          return (
            <div
              key={leg.id}
              className={`flex items-center gap-3 text-xs px-1 py-0.5 rounded
                ${isBlocked ? 'bg-accent-critical/8 border border-accent-critical/20' : ''}`}
            >
              {/* Mode badge */}
              <span
                className="w-1.5 h-1.5 rounded-full shrink-0"
                style={{ backgroundColor: isBlocked ? '#e84040' : MODE_COLOUR[leg.mode] ?? '#7e94b4' }}
                aria-hidden="true"
              />
              <span className={`shrink-0 w-12 ${isBlocked ? 'text-accent-critical font-medium' : 'text-text-muted'}`}>
                {MODE_LABEL[leg.mode]}
              </span>
              <span className="text-text-muted shrink-0">{leg.carrier}</span>
              <span className="text-text-muted">·</span>
              <span className="text-text-primary">{leg.from.label}</span>
              <span className="text-text-muted">→</span>
              <span className="text-text-primary">{leg.to.label}</span>
              <span className="flex-1" />
              <span
                className={`shrink-0 tabular-nums text-[10px]
                  ${isBlocked ? 'text-accent-critical font-medium' : 'text-text-muted'}`}
              >
                {STATUS_LABEL[leg.status]}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
