/**
 * StaticExcursionTrace.tsx — Static SVG temperature trace for auth screens.
 *
 * Uses a subset of shp-103 sensor data hard-coded here (not through the adapter —
 * this is a public marketing visual, not a data-driven component).
 * Shows the temperature climbing from safe range (2–8°C) to 24°C peak
 * with the excursion region shaded red and a severity badge.
 *
 * Designed for the right panel of the auth layout and login page.
 * Width: fills container. Height: 260px.
 */
import React from 'react';

// Minimal representative subset of shp-103 readings:
// starts in-range, climbs, breaches, peaks, stays above range
const READINGS = [
  { t: 0,    temp: 5.2 },
  { t: 30,   temp: 5.8 },
  { t: 60,   temp: 6.4 },
  { t: 90,   temp: 7.1 },
  { t: 120,  temp: 7.9 },  // about to breach
  { t: 135,  temp: 8.3 },  // first breach
  { t: 150,  temp: 9.6 },
  { t: 180,  temp: 12.1 },
  { t: 210,  temp: 15.4 },
  { t: 240,  temp: 18.7 },
  { t: 270,  temp: 21.3 },
  { t: 300,  temp: 23.1 },
  { t: 330,  temp: 24.2 }, // peak
  { t: 360,  temp: 23.8 },
  { t: 390,  temp: 22.5 },
  { t: 420,  temp: 20.1 },
  { t: 450,  temp: 17.6 },
  { t: 480,  temp: 14.2 },
  { t: 510,  temp: 11.8 },
  { t: 540,  temp: 10.1 },
  { t: 570,  temp: 9.4 },
  { t: 600,  temp: 9.1 },
];

const TEMP_MIN = 2;
const TEMP_MAX = 8;
const BREACH_TEMP = TEMP_MAX;

const W = 520;
const H = 200;
const PAD = { top: 16, right: 20, bottom: 32, left: 44 };
const CHART_W = W - PAD.left - PAD.right;
const CHART_H = H - PAD.top - PAD.bottom;

const DATA_TEMP_MIN = 0;
const DATA_TEMP_MAX = 28;

function xScale(t: number): number {
  const maxT = READINGS[READINGS.length - 1].t;
  return PAD.left + (t / maxT) * CHART_W;
}

function yScale(temp: number): number {
  return PAD.top + CHART_H - ((temp - DATA_TEMP_MIN) / (DATA_TEMP_MAX - DATA_TEMP_MIN)) * CHART_H;
}

function buildPath(readings: typeof READINGS): string {
  return readings
    .map((r, i) => `${i === 0 ? 'M' : 'L'} ${xScale(r.t).toFixed(1)} ${yScale(r.temp).toFixed(1)}`)
    .join(' ');
}

// Breach region: from t=135 to t=600 (still open)
const breachStartX = xScale(135);
const breachEndX = xScale(600);
const breachY1 = yScale(DATA_TEMP_MAX); // top of chart
const breachY2 = yScale(BREACH_TEMP);   // y at 8°C line (bottom of breach area)

export function StaticExcursionTrace() {
  const path = buildPath(READINGS);

  return (
    <div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        width="100%"
        height="260"
        aria-label="Temperature trace for shp-103 showing a critical cold-chain excursion"
        role="img"
      >
        {/* ── Allowed band ── */}
        <rect
          x={PAD.left}
          y={yScale(TEMP_MAX)}
          width={CHART_W}
          height={yScale(TEMP_MIN) - yScale(TEMP_MAX)}
          fill="#1a7a8a"
          fillOpacity={0.08}
        />

        {/* ── Excursion region ── */}
        <rect
          x={breachStartX}
          y={breachY1}
          width={breachEndX - breachStartX}
          height={breachY2 - breachY1}
          fill="#c0392b"
          fillOpacity={0.12}
        />

        {/* ── Grid lines ── */}
        {[0, 8, 16, 24].map((temp) => (
          <line
            key={temp}
            x1={PAD.left}
            y1={yScale(temp)}
            x2={PAD.left + CHART_W}
            y2={yScale(temp)}
            stroke="#d6d0c8"
            strokeWidth={0.5}
          />
        ))}

        {/* ── Limit lines ── */}
        <line
          x1={PAD.left} y1={yScale(TEMP_MAX)}
          x2={PAD.left + CHART_W} y2={yScale(TEMP_MAX)}
          stroke="#1a7a8a" strokeWidth={1} strokeDasharray="4 3"
        />
        <line
          x1={PAD.left} y1={yScale(TEMP_MIN)}
          x2={PAD.left + CHART_W} y2={yScale(TEMP_MIN)}
          stroke="#1a7a8a" strokeWidth={1} strokeDasharray="4 3"
        />

        {/* ── Temperature path ── */}
        <path d={path} fill="none" stroke="#1a7a8a" strokeWidth={2} strokeLinecap="round" />

        {/* ── Breach start marker ── */}
        <circle cx={xScale(135)} cy={yScale(8.3)} r={3} fill="#c0392b" />

        {/* ── Peak marker + label ── */}
        <circle cx={xScale(330)} cy={yScale(24.2)} r={3} fill="#c0392b" />
        <text
          x={xScale(330) + 6}
          y={yScale(24.2) - 4}
          fontSize={10}
          fill="#c0392b"
          fontFamily="'IBM Plex Mono', monospace"
        >
          24.2°C peak
        </text>

        {/* ── Y axis labels ── */}
        {[0, 8, 16, 24].map((temp) => (
          <text
            key={temp}
            x={PAD.left - 6}
            y={yScale(temp) + 4}
            fontSize={9}
            fill="#6b6560"
            textAnchor="end"
            fontFamily="'IBM Plex Mono', monospace"
          >
            {temp}°C
          </text>
        ))}

        {/* ── Allowed range label ── */}
        <text
          x={PAD.left + 6}
          y={yScale((TEMP_MIN + TEMP_MAX) / 2) + 4}
          fontSize={9}
          fill="#1a7a8a"
          fontFamily="'IBM Plex Mono', monospace"
        >
          2–8°C allowed
        </text>

        {/* ── Open breach label ── */}
        <text
          x={xScale(600) - 6}
          y={yScale(9.5)}
          fontSize={9}
          fill="#c0392b"
          textAnchor="end"
          fontFamily="'IBM Plex Mono', monospace"
        >
          ⚠ open breach
        </text>

        {/* ── X axis time labels ── */}
        {[0, 120, 240, 360, 480, 600].map((t) => (
          <text
            key={t}
            x={xScale(t)}
            y={H - PAD.bottom + 16}
            fontSize={9}
            fill="#6b6560"
            textAnchor="middle"
            fontFamily="'IBM Plex Mono', monospace"
          >
            +{t}m
          </text>
        ))}
      </svg>

      {/* Caption */}
      <div className="mt-3 space-y-1.5">
        <div
          className="flex items-center gap-2 text-xs font-mono"
          style={{ color: '#c0392b', fontFamily: "'IBM Plex Mono', monospace" }}
        >
          <span
            className="inline-block w-3 h-3 rounded-sm shrink-0"
            style={{ background: '#c0392b', opacity: 0.6 }}
            aria-hidden="true"
          />
          <span>◆ CRIT · shp-103 · 24.87°C peak · 21,040 deg-min · FSMA 21 CFR §1.908(b)(1)</span>
        </div>
        <p className="text-xs" style={{ color: '#6b6560', fontFamily: "'IBM Plex Mono', monospace" }}>
          Detected before delivery. Actionable.
        </p>
      </div>
    </div>
  );
}
