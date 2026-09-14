import { describe, it, expect } from 'vitest';
import {
  classifyExcursionSeverity,
  calculateDegreeMinutes,
  compareSeverity,
  severityRank,
  formatSeverityLine,
  SEVERITY_LABEL,
  SEVERITY_SHAPE,
} from '@/lib/utils/severity';
import type { Excursion } from '@/types/domain';

describe('severityRank', () => {
  it('assigns ascending ranks informational < minor < major < critical', () => {
    expect(severityRank('informational')).toBeLessThan(severityRank('minor'));
    expect(severityRank('minor')).toBeLessThan(severityRank('major'));
    expect(severityRank('major')).toBeLessThan(severityRank('critical'));
  });

  it('informational has rank 0', () => {
    expect(severityRank('informational')).toBe(0);
  });

  it('critical has highest rank', () => {
    const ranks = ['informational', 'minor', 'major', 'critical'].map(
      (s) => severityRank(s as 'informational'),
    );
    expect(severityRank('critical')).toBe(Math.max(...ranks));
  });
});

describe('compareSeverity', () => {
  it('sorts critical before major (returns negative)', () => {
    expect(compareSeverity('critical', 'major')).toBeLessThan(0);
  });

  it('sorts major before minor', () => {
    expect(compareSeverity('major', 'minor')).toBeLessThan(0);
  });

  it('sorts minor before informational', () => {
    expect(compareSeverity('minor', 'informational')).toBeLessThan(0);
  });

  it('equal severity returns 0', () => {
    expect(compareSeverity('minor', 'minor')).toBe(0);
    expect(compareSeverity('critical', 'critical')).toBe(0);
  });

  it('produces correct order when used in Array.sort', () => {
    const severities: Array<'informational' | 'minor' | 'major' | 'critical'> = [
      'minor', 'critical', 'informational', 'major',
    ];
    const sorted = [...severities].sort(compareSeverity);
    expect(sorted).toEqual(['critical', 'major', 'minor', 'informational']);
  });
});

describe('classifyExcursionSeverity', () => {
  it('returns informational for very short, low-magnitude excursion', () => {
    expect(classifyExcursionSeverity(10, 5)).toBe('informational');
  });

  it('returns informational for <15 min and <10 deg-min', () => {
    expect(classifyExcursionSeverity(14, 9)).toBe('informational');
  });

  it('returns minor for 30min excursion with 30 deg-min', () => {
    expect(classifyExcursionSeverity(30, 30)).toBe('minor');
  });

  it('returns minor up to 120 min and 50 deg-min', () => {
    expect(classifyExcursionSeverity(119, 49)).toBe('minor');
  });

  it('returns major for 150min excursion with 100 deg-min', () => {
    expect(classifyExcursionSeverity(150, 100)).toBe('major');
  });

  it('returns major for 2–4h excursion range', () => {
    expect(classifyExcursionSeverity(200, 120)).toBe('major');
  });

  it('returns critical for >4h excursion', () => {
    expect(classifyExcursionSeverity(300, 250)).toBe('critical');
  });

  it('returns critical for high degree-minutes regardless of duration', () => {
    expect(classifyExcursionSeverity(100, 210)).toBe('critical');
  });

  // Fixture-matching cases
  it('classifies shp-103 breach (432 deg-min, 120 min) as critical', () => {
    expect(classifyExcursionSeverity(120, 432)).toBe('critical');
  });

  it('classifies shp-104 breach (48 deg-min, 110 min) as minor', () => {
    expect(classifyExcursionSeverity(110, 48)).toBe('minor');
  });

  it('classifies shp-101 breach (12 deg-min, 40 min) as minor', () => {
    expect(classifyExcursionSeverity(40, 12)).toBe('minor');
  });
});

describe('calculateDegreeMinutes', () => {
  it('returns 0 for empty series', () => {
    expect(calculateDegreeMinutes([], 8)).toBe(0);
  });

  it('returns 0 for single reading (no interval)', () => {
    expect(calculateDegreeMinutes([{ tempC: 10, timestampMs: 0 }], 8)).toBe(0);
  });

  it('calculates correctly for two readings 5 min apart at 2°C above limit', () => {
    const r = [
      { tempC: 10, timestampMs: 0 },
      { tempC: 10, timestampMs: 5 * 60 * 1000 },
    ];
    // avg = 10, limit = 8, dev = 2, Δt = 5 → 10
    expect(calculateDegreeMinutes(r, 8)).toBe(10);
  });

  it('accumulates correctly across multiple readings', () => {
    const r = [
      { tempC: 9, timestampMs: 0 },
      { tempC: 11, timestampMs: 5 * 60 * 1000 },
      { tempC: 11, timestampMs: 10 * 60 * 1000 },
    ];
    // Interval 1: avg = 10, dev = 2, Δt = 5 → 10
    // Interval 2: avg = 11, dev = 3, Δt = 5 → 15
    // Total = 25
    expect(calculateDegreeMinutes(r, 8)).toBe(25);
  });

  it('works with negative temperatures (frozen cargo)', () => {
    const r = [
      { tempC: -17, timestampMs: 0 },
      { tempC: -17, timestampMs: 5 * 60 * 1000 },
    ];
    // avg = -17, limit = -18 (max), dev = |-17 - -18| = 1, Δt = 5 → 5
    expect(calculateDegreeMinutes(r, -18)).toBe(5);
  });

  it('handles readings below minimum limit', () => {
    const r = [
      { tempC: -22, timestampMs: 0 },
      { tempC: -22, timestampMs: 5 * 60 * 1000 },
    ];
    // avg = -22, limit = -20 (min), dev = |-22 - -20| = 2, Δt = 5 → 10
    expect(calculateDegreeMinutes(r, -20)).toBe(10);
  });
});

describe('formatSeverityLine', () => {
  it('contains the correct shape for critical (diamond)', () => {
    const exc: Partial<Excursion> = { severity: 'critical', degreeMinutes: 432, minutesOutOfRange: 130 };
    expect(formatSeverityLine(exc as Excursion)).toContain(SEVERITY_SHAPE.critical);
  });

  it('contains the correct label text', () => {
    const exc: Partial<Excursion> = { severity: 'critical', degreeMinutes: 432, minutesOutOfRange: 130 };
    expect(formatSeverityLine(exc as Excursion)).toContain(SEVERITY_LABEL.critical);
  });

  it('formats degree-minutes in the output', () => {
    const exc: Partial<Excursion> = { severity: 'major', degreeMinutes: 142, minutesOutOfRange: 200 };
    expect(formatSeverityLine(exc as Excursion)).toContain('142 deg-min');
  });

  it('formats hours and minutes correctly for 130 min', () => {
    const exc: Partial<Excursion> = { severity: 'critical', degreeMinutes: 432, minutesOutOfRange: 130 };
    expect(formatSeverityLine(exc as Excursion)).toContain('2h 10m');
  });

  it('formats sub-hour duration without hours component', () => {
    const exc: Partial<Excursion> = { severity: 'minor', degreeMinutes: 48, minutesOutOfRange: 45 };
    const result = formatSeverityLine(exc as Excursion);
    expect(result).toContain('45m');
    expect(result).not.toMatch(/\dh/);
  });

  it('formats exact-hour duration correctly', () => {
    const exc: Partial<Excursion> = { severity: 'major', degreeMinutes: 80, minutesOutOfRange: 120 };
    expect(formatSeverityLine(exc as Excursion)).toContain('2h 0m');
  });

  it('never uses colour as sole carrier — always includes shape and label', () => {
    (['informational', 'minor', 'major', 'critical'] as const).forEach((sev) => {
      const exc: Partial<Excursion> = { severity: sev, degreeMinutes: 10, minutesOutOfRange: 20 };
      const result = formatSeverityLine(exc as Excursion);
      expect(result).toContain(SEVERITY_SHAPE[sev]);
      expect(result).toContain(SEVERITY_LABEL[sev]);
    });
  });
});
