/**
 * LandingPage.tsx — Public landing page for Coldfront.
 *
 * Sections:
 *   1. Above the fold — hero trace animation + two CTAs
 *   2. The four questions
 *   3. Degree-minutes explainer (the differentiator)
 *   4. How it works (five steps)
 *   5. Built with IBM Bob
 *   6. Footer
 *
 * Light register: warm off-white (#f5f2ee) — deliberately different from the
 * dark app (#0e1621) so logging in feels like stepping from daylight into a
 * control room.
 *
 * An authenticated visit redirects to /tower.
 * The backend does not need to be running — all content is static.
 *
 * prefers-reduced-motion: hero renders in final state, all animations disabled.
 */
import React, { useEffect, useRef, useState } from 'react';
import { Navigate, Link } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';

// ── Palette ───────────────────────────────────────────────────────────────────
const C = {
  bg: '#f5f2ee',
  surface: '#ece8e2',
  border: '#d6d0c8',
  text: '#1a1814',
  muted: '#6b6560',
  accent: '#b85c14',
  teal: '#1a7a8a',
  critical: '#c0392b',
  dark: '#1a1814',
} as const;

// ── Hero trace data (shp-101: starts in-range, then breaches 8°C) ─────────────
// 60 points sampled from the fixture — starts at 5.7°C, climbs, breaches at ~22h
const HERO_READINGS = [
  5.69, 6.52, 6.76, 7.07, 7.28, 7.46, 7.64, 7.82, 8.07, 8.31,
  8.62, 8.95, 9.28, 9.74, 10.1, 10.52, 10.95, 11.4, 11.85, 12.1,
  11.82, 11.41, 10.95, 10.42, 9.88, 9.31, 8.72, 8.21, 7.84, 7.52,
  7.24, 7.01, 6.82, 6.65, 6.51, 6.38, 6.27, 6.17, 6.08, 6.01,
  5.95, 5.89, 5.84, 5.80, 5.77, 5.74, 5.72, 5.70, 5.69, 5.68,
  5.68, 5.67, 5.67, 5.67, 5.66, 5.66, 5.66, 5.65, 5.65, 5.65,
];

const TEMP_MIN = 2;
const TEMP_MAX = 8;

// SVG canvas for hero
const HW = 600;
const HH = 180;
const HPAD = { top: 12, right: 16, bottom: 28, left: 40 };
const HCHART_W = HW - HPAD.left - HPAD.right;
const HCHART_H = HH - HPAD.top - HPAD.bottom;
const H_DATA_MIN = 0;
const H_DATA_MAX = 16;

function hx(i: number, total: number): number {
  return HPAD.left + (i / (total - 1)) * HCHART_W;
}
function hy(temp: number): number {
  return HPAD.top + HCHART_H - ((temp - H_DATA_MIN) / (H_DATA_MAX - H_DATA_MIN)) * HCHART_H;
}

function buildHeroPath(readings: number[]): string {
  return readings
    .map((temp, i) => `${i === 0 ? 'M' : 'L'} ${hx(i, readings.length).toFixed(1)} ${hy(temp).toFixed(1)}`)
    .join(' ');
}

// Index where breach starts (first point > 8°C)
const BREACH_IDX = HERO_READINGS.findIndex((t) => t > TEMP_MAX);

// ── Animated hero trace ───────────────────────────────────────────────────────
function HeroTrace() {
  const pathRef = useRef<SVGPathElement>(null);
  const [drawn, setDrawn] = useState(0); // 0–1 animation progress
  const [showExcursion, setShowExcursion] = useState(false);
  const [showBadge, setShowBadge] = useState(false);
  const rafRef = useRef<number>(0);
  const startRef = useRef<number | null>(null);
  const DURATION = 3000; // ms

  const prefersReduced =
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  useEffect(() => {
    if (prefersReduced) {
      setDrawn(1);
      setShowExcursion(true);
      setShowBadge(true);
      return;
    }

    function animate(ts: number) {
      if (startRef.current === null) startRef.current = ts;
      const elapsed = ts - startRef.current;
      const progress = Math.min(elapsed / DURATION, 1);
      setDrawn(progress);

      // Show excursion region when we've drawn past the breach point
      if (progress >= BREACH_IDX / HERO_READINGS.length) {
        setShowExcursion(true);
      }
      // Show badge when animation completes
      if (progress >= 1) {
        setShowBadge(true);
        return;
      }
      rafRef.current = requestAnimationFrame(animate);
    }

    rafRef.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(rafRef.current);
  }, [prefersReduced]);

  // Build the full path length for stroke-dashoffset animation
  const fullPath = buildHeroPath(HERO_READINGS);

  // Partial path for drawn portion
  const drawnCount = Math.max(2, Math.round(drawn * HERO_READINGS.length));
  const partialPath = buildHeroPath(HERO_READINGS.slice(0, drawnCount));

  // Excursion region: x from breach to end
  const breachX = hx(BREACH_IDX, HERO_READINGS.length);
  const endX = hx(HERO_READINGS.length - 1, HERO_READINGS.length);
  const excursionTop = hy(H_DATA_MAX);
  const excursionBottom = hy(TEMP_MAX);

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${HW} ${HH}`}
        width="100%"
        aria-label="Animated temperature trace showing a cold-chain excursion"
        role="img"
        style={{ display: 'block' }}
      >
        {/* Allowed band */}
        <rect
          x={HPAD.left}
          y={hy(TEMP_MAX)}
          width={HCHART_W}
          height={hy(TEMP_MIN) - hy(TEMP_MAX)}
          fill={C.teal}
          fillOpacity={0.07}
        />

        {/* Grid */}
        {[0, 4, 8, 12, 16].map((t) => (
          <line
            key={t}
            x1={HPAD.left} y1={hy(t)}
            x2={HPAD.left + HCHART_W} y2={hy(t)}
            stroke={C.border} strokeWidth={0.5}
          />
        ))}

        {/* Limit lines */}
        <line
          x1={HPAD.left} y1={hy(TEMP_MAX)}
          x2={HPAD.left + HCHART_W} y2={hy(TEMP_MAX)}
          stroke={C.teal} strokeWidth={1} strokeDasharray="4 3"
        />
        <line
          x1={HPAD.left} y1={hy(TEMP_MIN)}
          x2={HPAD.left + HCHART_W} y2={hy(TEMP_MIN)}
          stroke={C.teal} strokeWidth={1} strokeDasharray="4 3"
        />

        {/* Excursion region (fades in when breach is reached) */}
        {showExcursion && (
          <rect
            x={breachX}
            y={excursionTop}
            width={endX - breachX}
            height={excursionBottom - excursionTop}
            fill={C.critical}
            fillOpacity={0.15}
            style={prefersReduced ? {} : { animation: 'fadeIn 0.4s ease' }}
          />
        )}

        {/* Drawn path */}
        <path
          d={prefersReduced ? fullPath : partialPath}
          fill="none"
          stroke={C.teal}
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {/* Y axis labels */}
        {[0, 4, 8, 12, 16].map((t) => (
          <text
            key={t}
            x={HPAD.left - 4}
            y={hy(t) + 4}
            fontSize={9}
            fill={C.muted}
            textAnchor="end"
            fontFamily="'IBM Plex Mono', monospace"
          >
            {t}°C
          </text>
        ))}

        {/* Range label */}
        <text
          x={HPAD.left + 6}
          y={hy(5) + 4}
          fontSize={9}
          fill={C.teal}
          fontFamily="'IBM Plex Mono', monospace"
        >
          allowed 2–8°C
        </text>

        {/* X axis */}
        <text x={HPAD.left} y={HH - 6} fontSize={9} fill={C.muted} fontFamily="'IBM Plex Mono', monospace">
          +0h
        </text>
        <text x={hx(30, 60)} y={HH - 6} fontSize={9} fill={C.muted} textAnchor="middle" fontFamily="'IBM Plex Mono', monospace">
          +12h
        </text>
        <text x={hx(59, 60)} y={HH - 6} fontSize={9} fill={C.muted} textAnchor="end" fontFamily="'IBM Plex Mono', monospace">
          +24h
        </text>
      </svg>

      {/* Severity badge (fades in after animation) */}
      {showBadge && (
        <div
          className="mt-3 inline-flex items-center gap-2 text-xs font-mono px-3 py-1.5 rounded-full"
          style={{
            background: `${C.critical}18`,
            border: `1px solid ${C.critical}40`,
            color: C.critical,
            fontFamily: "'IBM Plex Mono', monospace",
            animation: prefersReduced ? undefined : 'fadeIn 0.4s ease',
          }}
          role="status"
          aria-label="Critical temperature excursion detected"
        >
          ◆ CRIT · shp-101 · 12.69°C peak · 3,114 deg-min · GDP Annex 5.5
        </div>
      )}

      <style>{`
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
      `}</style>
    </div>
  );
}

// ── Degree-minutes comparison ─────────────────────────────────────────────────

function MiniTrace({
  label,
  readings,
  highlight,
  degMin,
  color,
}: {
  label: string;
  readings: number[];
  highlight: boolean;
  degMin: number;
  color: string;
}) {
  const W = 200, H = 90;
  const PAD = { top: 8, right: 8, bottom: 20, left: 32 };
  const CW = W - PAD.left - PAD.right;
  const CH = H - PAD.top - PAD.bottom;
  const DMIN = 0, DMAX = 30;

  function mx(i: number) { return PAD.left + (i / (readings.length - 1)) * CW; }
  function my(t: number) { return PAD.top + CH - ((t - DMIN) / (DMAX - DMIN)) * CH; }

  const path = readings
    .map((t, i) => `${i === 0 ? 'M' : 'L'} ${mx(i).toFixed(1)} ${my(t).toFixed(1)}`)
    .join(' ');

  // Area above 8°C
  const areaPoints = readings
    .map((t, i) => ({ x: mx(i), y: my(Math.min(t, DMAX)) }))
    .filter((_) => true);
  const areaPath = readings
    .map((t, i) => {
      const y = my(Math.max(t, TEMP_MAX));
      return `${i === 0 ? 'M' : 'L'} ${mx(i).toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(' ') +
    ` L ${mx(readings.length - 1).toFixed(1)} ${my(TEMP_MAX).toFixed(1)}` +
    ` L ${mx(0).toFixed(1)} ${my(TEMP_MAX).toFixed(1)} Z`;

  return (
    <div className="text-center">
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ maxWidth: 200, display: 'block', margin: '0 auto' }}>
        {/* 8°C limit line */}
        <line
          x1={PAD.left} y1={my(TEMP_MAX)}
          x2={PAD.left + CW} y2={my(TEMP_MAX)}
          stroke={C.teal} strokeWidth={1} strokeDasharray="3 2"
        />
        {/* Area above limit */}
        {highlight && (
          <path d={areaPath} fill={color} fillOpacity={0.18} />
        )}
        {/* Line */}
        <path d={path} fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" />
        {/* Y axis labels */}
        {[0, 8, 16, 24].map((t) => (
          <text key={t} x={PAD.left - 3} y={my(t) + 3} fontSize={7} fill={C.muted} textAnchor="end" fontFamily="'IBM Plex Mono', monospace">
            {t}°
          </text>
        ))}
      </svg>
      <p className="text-xs font-mono mt-1" style={{ color, fontFamily: "'IBM Plex Mono', monospace" }}>
        {degMin} deg-min above 8°C
      </p>
      <p className="text-xs mt-0.5" style={{ color: C.muted }}>{label}</p>
    </div>
  );
}

function DegreeMinutesComparison() {
  // Trace A: 30 min at 25°C — 7 readings at 25°C
  const traceA = Array(7).fill(25);
  // Trace B: 30 min at 8.5°C — 7 readings at 8.5°C
  const traceB = Array(7).fill(8.5);

  return (
    <section
      className="py-16 px-6"
      style={{ background: C.surface, borderTop: `1px solid ${C.border}`, borderBottom: `1px solid ${C.border}` }}
    >
      <div className="max-w-2xl mx-auto">
        <h2 className="font-semibold mb-3" style={{ color: C.text, fontSize: 'clamp(1.25rem, 2.5vw, 1.875rem)' }}>
          Not all excursions are equal
        </h2>
        <p className="mb-8" style={{ color: C.muted, fontSize: 'clamp(0.9375rem, 1.5vw, 1rem)', maxWidth: 560 }}>
          A threshold alarm treats these the same event. Coldfront does not.
        </p>
        <div className="flex gap-8 justify-center flex-wrap mb-6">
          <MiniTrace
            label="30 min at 25°C"
            readings={traceA}
            highlight
            degMin={510}
            color={C.critical}
          />
          <div className="flex items-center" style={{ color: C.muted, fontSize: 20 }}>vs</div>
          <MiniTrace
            label="30 min at 8.5°C"
            readings={traceB}
            highlight
            degMin={15}
            color={C.accent}
          />
        </div>
        <p className="text-sm" style={{ color: C.muted, maxWidth: 520 }}>
          Trace A accumulates <strong style={{ color: C.critical }}>510 deg-min</strong> above range.
          Trace B accumulates <strong style={{ color: C.accent }}>15</strong>.
          The difference determines whether cargo is quarantined, relabelled, or released —
          and who signs off under GDP Annex 5.5 or FSMA 21 CFR §1.908(b)(1).
        </p>
      </div>
    </section>
  );
}

// ── Scroll reveal wrapper ─────────────────────────────────────────────────────
function Reveal({ children, delay = 0 }: { children: React.ReactNode; delay?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const prefersReduced =
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  useEffect(() => {
    if (prefersReduced) { setVisible(true); return; }
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) { setVisible(true); obs.disconnect(); } },
      { threshold: 0.15 },
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [prefersReduced]);

  return (
    <div
      ref={ref}
      style={{
        opacity: visible ? 1 : 0,
        transform: visible ? 'translateY(0)' : 'translateY(12px)',
        transition: prefersReduced ? undefined : `opacity 0.3s ease ${delay}ms, transform 0.3s ease ${delay}ms`,
      }}
    >
      {children}
    </div>
  );
}

// ── Landing page ──────────────────────────────────────────────────────────────
export function LandingPage() {
  const { status } = useAuth();

  // Redirect authenticated users to the app
  if (status === 'authed') {
    return <Navigate to="/tower" replace />;
  }

  return (
    <div style={{ background: C.bg, color: C.text, fontFamily: "'IBM Plex Sans', 'Segoe UI', system-ui, sans-serif" }}>
      {/* ── Nav ── */}
      <nav
        className="flex items-center justify-between px-6 sm:px-10 py-4 sticky top-0 z-30"
        style={{ background: `${C.bg}e8`, backdropFilter: 'blur(8px)', borderBottom: `1px solid ${C.border}` }}
      >
        <span className="font-semibold" style={{ color: C.text }}>Coldfront</span>
        <div className="flex items-center gap-3">
          <Link
            to="/login"
            className="px-4 py-2 rounded text-sm outline-none focus-visible:ring-2 transition-colors"
            style={{ color: C.muted, minHeight: 44, display: 'inline-flex', alignItems: 'center' }}
          >
            Sign in
          </Link>
          <Link
            to="/tower"
            className="px-4 py-2 rounded text-sm font-medium outline-none focus-visible:ring-2 transition-colors"
            style={{ background: C.dark, color: '#f5f2ee', minHeight: 44, display: 'inline-flex', alignItems: 'center' }}
          >
            Enter demo
          </Link>
        </div>
      </nav>

      {/* ── 1. Above the fold ── */}
      <section className="px-6 sm:px-10 pt-16 pb-12 max-w-5xl mx-auto">
        <div className="grid md:grid-cols-2 gap-10 items-center">
          <div>
            <Reveal>
              <h1
                className="font-semibold leading-tight mb-4"
                style={{ color: C.text, fontSize: 'clamp(2rem, 4vw, 3.5rem)' }}
              >
                A control tower for pharmaceutical cold chain.
              </h1>
              <p
                className="mb-8 leading-relaxed"
                style={{ color: C.muted, fontSize: 'clamp(0.9375rem, 1.5vw, 1.0625rem)', maxWidth: 440 }}
              >
                For operators managing hundreds of active shipments who need to know, right now,
                which ones are hit and what to do.
              </p>
              <div className="flex gap-3 flex-wrap">
                <Link
                  to="/tower"
                  className="px-6 py-3 rounded font-medium text-sm outline-none focus-visible:ring-2 transition-colors"
                  style={{ background: C.dark, color: '#f5f2ee', minHeight: 44, display: 'inline-flex', alignItems: 'center' }}
                >
                  Enter demo →
                </Link>
                <Link
                  to="/login"
                  className="px-6 py-3 rounded font-medium text-sm outline-none focus-visible:ring-2 transition-colors"
                  style={{
                    border: `1px solid ${C.border}`,
                    color: C.text,
                    minHeight: 44,
                    display: 'inline-flex',
                    alignItems: 'center',
                  }}
                >
                  Sign in
                </Link>
              </div>
            </Reveal>
          </div>

          {/* Hero trace */}
          <div>
            <Reveal delay={100}>
              <HeroTrace />
            </Reveal>
          </div>
        </div>
      </section>

      {/* ── 2. The four questions ── */}
      <section
        className="py-14 px-6 sm:px-10"
        style={{ borderTop: `1px solid ${C.border}` }}
      >
        <div className="max-w-2xl mx-auto">
          <Reveal>
            <h2
              className="font-semibold mb-8"
              style={{ color: C.text, fontSize: 'clamp(1.25rem, 2.5vw, 1.875rem)' }}
            >
              Four questions. One screen. Seconds.
            </h2>
          </Reveal>
          <ol className="space-y-4">
            {[
              'Which shipments are affected by this disruption, and how badly?',
              'What are the rerouting options that preserve cold-chain continuity?',
              'Which fleet assets are idle and deployable right now?',
              'Which cold-chain cargo has breached its temperature envelope while there is still time to act?',
            ].map((q, i) => (
              <Reveal key={i} delay={i * 60}>
                <li className="flex items-start gap-4">
                  <span
                    className="shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-mono font-bold mt-0.5"
                    style={{ background: C.surface, border: `1px solid ${C.border}`, color: C.muted }}
                  >
                    {i + 1}
                  </span>
                  <p style={{ color: C.text, fontSize: 'clamp(0.9375rem, 1.5vw, 1rem)', lineHeight: 1.6 }}>{q}</p>
                </li>
              </Reveal>
            ))}
          </ol>
        </div>
      </section>

      {/* ── 3. Degree-minutes explainer ── */}
      <Reveal>
        <DegreeMinutesComparison />
      </Reveal>

      {/* ── 4. How it works ── */}
      <section className="py-14 px-6 sm:px-10" style={{ borderBottom: `1px solid ${C.border}` }}>
        <div className="max-w-2xl mx-auto">
          <Reveal>
            <h2 className="font-semibold mb-8" style={{ color: C.text, fontSize: 'clamp(1.25rem, 2.5vw, 1.875rem)' }}>
              How it works
            </h2>
          </Reveal>
          <ol className="space-y-5">
            {[
              ['Observe', 'Ingest sensor readings at five-minute intervals.'],
              ['Quantify', 'Compute degree-minutes and Arrhenius mean kinetic temperature.'],
              ['Classify', 'Match against versioned YAML rule packs (GDP, WHO PQS, USP ⟨1079⟩, FSMA).'],
              ['Rank', 'Score by severity, actionability, cargo value, and time remaining.'],
              ['Explain', 'The model translates the verdict to plain language. It never produces one.'],
            ].map(([step, desc], i) => (
              <Reveal key={i} delay={i * 60}>
                <li className="flex items-start gap-4">
                  <span
                    className="shrink-0 text-xs font-mono font-semibold w-20 pt-0.5"
                    style={{ color: C.teal }}
                  >
                    {step}
                  </span>
                  <p style={{ color: C.muted, fontSize: 'clamp(0.9375rem, 1.5vw, 1rem)' }}>{desc}</p>
                </li>
              </Reveal>
            ))}
          </ol>
        </div>
      </section>

      {/* ── 5. Built with IBM Bob ── */}
      <section className="py-14 px-6 sm:px-10" style={{ borderBottom: `1px solid ${C.border}` }}>
        <div className="max-w-2xl mx-auto">
          <Reveal>
            <h2 className="font-semibold mb-4" style={{ color: C.text, fontSize: 'clamp(1.25rem, 2.5vw, 1.875rem)' }}>
              Built with IBM Bob
            </h2>
            <p style={{ color: C.muted, fontSize: 'clamp(0.9375rem, 1.5vw, 1rem)', lineHeight: 1.7 }}>
              Coldfront was built in eight phases with IBM Bob. Bob planned the architecture in Plan
              mode before a line was written — the route and data-flow map, the cold-chain engine
              pipeline, the decision-object schema. Implementation ran phase by phase: backend engines
              first, then the API layer, then the frontend adapter and components. Bob reviewed the
              excursion classification logic against the four regulatory rule packs and caught a case
              where degree-minutes accumulated across a sensor gap were being attributed to the wrong
              leg — a bug invisible without a trace-through. The session exports in{' '}
              <code
                className="px-1 py-0.5 rounded text-xs"
                style={{ background: C.surface, fontFamily: "'IBM Plex Mono', monospace" }}
              >
                bob_sessions/
              </code>{' '}
              show that work.
            </p>
          </Reveal>
        </div>
      </section>

      {/* ── 6. Footer ── */}
      <footer className="py-10 px-6 sm:px-10">
        <div className="max-w-2xl mx-auto flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex gap-5 flex-wrap">
            <a
              href="https://github.com"
              className="text-sm underline outline-none focus-visible:ring-2"
              style={{ color: C.muted }}
            >
              GitHub
            </a>
            <a
              href="/demo/demo-video-link.txt"
              className="text-sm underline outline-none focus-visible:ring-2"
              style={{ color: C.muted }}
            >
              Demo video
            </a>
            <a
              href="/docs/setup-guide.md"
              className="text-sm underline outline-none focus-visible:ring-2"
              style={{ color: C.muted }}
            >
              Setup guide
            </a>
          </div>
          <p className="text-xs" style={{ color: C.muted, maxWidth: 340 }}>
            Proof of concept. All shipment, party, cargo, and sensor data is synthetic.
            Not for clinical or regulatory use. IBM Bob Hackathon 2025.
          </p>
        </div>
      </footer>
    </div>
  );
}
