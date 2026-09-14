import type { Severity, Excursion } from '@/types/domain';

// ─── Severity ordering ────────────────────────────────────────────────────────

const SEVERITY_RANK: Record<Severity, number> = {
  informational: 0,
  minor: 1,
  major: 2,
  critical: 3,
};

export function severityRank(s: Severity): number {
  return SEVERITY_RANK[s];
}

export function compareSeverity(a: Severity, b: Severity): number {
  return severityRank(b) - severityRank(a); // descending (critical first)
}

// ─── Display helpers ──────────────────────────────────────────────────────────

export const SEVERITY_LABEL: Record<Severity, string> = {
  informational: 'INFO',
  minor: 'MINOR',
  major: 'MAJOR',
  critical: 'CRIT',
};

/** Tailwind text-colour class for a severity */
export const SEVERITY_TEXT_CLASS: Record<Severity, string> = {
  informational: 'text-accent-minor',
  minor: 'text-accent-minor',
  major: 'text-accent-disruption',
  critical: 'text-accent-critical',
};

/** Tailwind bg-colour class for a severity badge */
export const SEVERITY_BG_CLASS: Record<Severity, string> = {
  informational: 'bg-accent-minor/10',
  minor: 'bg-accent-minor/10',
  major: 'bg-accent-disruption/10',
  critical: 'bg-accent-critical/10',
};

/**
 * Shape used alongside colour for colour-blind safety.
 * Rendered as a Unicode character — pair with the label, never use alone.
 */
export const SEVERITY_SHAPE: Record<Severity, string> = {
  informational: '●', // circle
  minor: '■', // square
  major: '▲', // triangle
  critical: '◆', // diamond
};

// ─── Classification ───────────────────────────────────────────────────────────

/**
 * Classifies an excursion severity based on degree-minutes and duration.
 * This mirrors the backend logic for the mock data; the backend value is
 * authoritative in production — the frontend displays it, not recomputes it.
 *
 * Thresholds are illustrative and based on GDP Annex 5.5 guidance:
 *   - <15 min out of range: informational
 *   - 15–120 min OR <50 deg-min: minor
 *   - 120–240 min OR 50–200 deg-min: major
 *   - >240 min OR >200 deg-min: critical
 */
export function classifyExcursionSeverity(
  minutesOutOfRange: number,
  degreeMinutes: number,
): Severity {
  if (minutesOutOfRange < 15 && degreeMinutes < 10) return 'informational';
  if (minutesOutOfRange < 120 && degreeMinutes < 50) return 'minor';
  if (minutesOutOfRange < 240 && degreeMinutes < 200) return 'major';
  return 'critical';
}

/**
 * Calculates degree-minutes for an excursion.
 * Formula: Σ(|T_i − T_limit| × Δt_minutes) for each reading outside range.
 *
 * @param readings  Array of {tempC, timestampMs} sorted by time
 * @param limitC    The breached limit (min or max of the allowed range)
 */
export function calculateDegreeMinutes(
  readings: Array<{ tempC: number; timestampMs: number }>,
  limitC: number,
): number {
  let total = 0;
  for (let i = 1; i < readings.length; i++) {
    const prev = readings[i - 1];
    const curr = readings[i];
    const deltaMinutes = (curr.timestampMs - prev.timestampMs) / 60_000;
    const avgTemp = (prev.tempC + curr.tempC) / 2;
    const deviation = Math.abs(avgTemp - limitC);
    total += deviation * deltaMinutes;
  }
  return Math.round(total * 10) / 10;
}

/**
 * Formats a severity for display with all required elements:
 * shape + label + driver context.
 */
export function formatSeverityLine(excursion: Excursion): string {
  const shape = SEVERITY_SHAPE[excursion.severity];
  const label = SEVERITY_LABEL[excursion.severity];
  const h = Math.floor(excursion.minutesOutOfRange / 60);
  const m = excursion.minutesOutOfRange % 60;
  const duration = h > 0 ? `${h}h ${m}m` : `${m}m`;
  return `${shape} ${label} · ${excursion.degreeMinutes} deg-min · ${duration} out of range`;
}
