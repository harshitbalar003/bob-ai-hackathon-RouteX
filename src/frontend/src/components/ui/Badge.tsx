import React from 'react';
import type { Severity } from '@/types/domain';
import {
  SEVERITY_LABEL,
  SEVERITY_TEXT_CLASS,
  SEVERITY_BG_CLASS,
  SEVERITY_SHAPE,
} from '@/lib/utils/severity';

interface BadgeProps {
  severity: Severity;
  className?: string;
}

/**
 * Severity badge: colour + shape + text label.
 * Never relies on colour alone (colour-blind safe).
 */
export function SeverityBadge({ severity, className = '' }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-medium tabular-nums
        ${SEVERITY_BG_CLASS[severity]} ${SEVERITY_TEXT_CLASS[severity]} ${className}`}
      aria-label={`Severity: ${SEVERITY_LABEL[severity]}`}
    >
      <span aria-hidden="true" className="text-[10px]">
        {SEVERITY_SHAPE[severity]}
      </span>
      {SEVERITY_LABEL[severity]}
    </span>
  );
}

interface StatusBadgeProps {
  label: string;
  variant: 'on_track' | 'at_risk' | 'delayed' | 'exception' | 'neutral';
  className?: string;
}

const STATUS_STYLES: Record<StatusBadgeProps['variant'], string> = {
  on_track: 'bg-accent-tracking/10 text-accent-tracking',
  at_risk: 'bg-accent-disruption/10 text-accent-disruption',
  delayed: 'bg-accent-disruption/20 text-accent-disruption',
  exception: 'bg-accent-critical/10 text-accent-critical',
  neutral: 'bg-surface-border/50 text-text-muted',
};

export function StatusBadge({ label, variant, className = '' }: StatusBadgeProps) {
  return (
    <span
      className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium
        ${STATUS_STYLES[variant]} ${className}`}
    >
      {label}
    </span>
  );
}
