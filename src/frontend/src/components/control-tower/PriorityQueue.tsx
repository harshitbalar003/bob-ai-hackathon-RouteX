import React from 'react';
import { useNavigate } from 'react-router-dom';
import { formatDistanceToNow } from 'date-fns';
import type { PriorityItem } from '@/types/domain';
import { SeverityBadge } from '@/components/ui/Badge';

interface PriorityQueueProps {
  items: PriorityItem[];
}

const KIND_LABEL: Record<PriorityItem['kind'], string> = {
  shipment_exception: 'Shipment',
  excursion: 'Temperature breach',
  idle_asset: 'Idle asset',
};

// Distinct left-edge colour per severity for scannable density
const SEVERITY_BORDER: Record<string, string> = {
  critical: 'border-l-accent-critical',
  major: 'border-l-accent-disruption',
  minor: 'border-l-surface-border',
  informational: 'border-l-surface-border',
};

const KIND_ICON: Record<PriorityItem['kind'], React.ReactNode> = {
  shipment_exception: (
    <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
      <polygon points="5,1 9,9 1,9" fill="none" stroke="currentColor" strokeWidth="1.2" />
    </svg>
  ),
  excursion: (
    <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
      <polygon points="5,1 9,5 5,9 1,5" fill="currentColor" />
    </svg>
  ),
  idle_asset: (
    <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
      <circle cx="5" cy="5" r="4" fill="none" stroke="currentColor" strokeWidth="1.2" />
    </svg>
  ),
};

export function PriorityQueue({ items }: PriorityQueueProps) {
  const navigate = useNavigate();

  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-32 text-text-muted text-sm gap-2">
        <span>No active exceptions</span>
        <span className="text-xs">All shipments on track</span>
      </div>
    );
  }

  return (
    <ol
      className="divide-y divide-surface-border"
      aria-label="Priority queue — ranked actions requiring attention"
      aria-live="polite"
      aria-atomic="false"
      aria-relevant="additions text"
    >
      {items.map((item, idx) => (
        <li key={item.id}>
          <button
            className={`w-full text-left pl-3 pr-4 py-2.5 border-l-2
              hover:bg-surface-raised/50 transition-colors duration-75
              focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-minor
              group ${SEVERITY_BORDER[item.severity] ?? 'border-l-surface-border'}`}
            onClick={() => navigate(item.href)}
            aria-label={`${KIND_LABEL[item.kind]}: ${item.headline}. ${item.stake}`}
          >
            <div className="flex items-start gap-2">
              {/* Rank number */}
              <span className="text-[10px] text-text-muted tabular-nums w-4 pt-0.5 shrink-0 font-mono-sensor">
                {String(idx + 1).padStart(2, '0')}
              </span>

              {/* Kind icon — colour matches severity */}
              <span
                className={`shrink-0 pt-1
                  ${item.severity === 'critical'
                    ? 'text-accent-critical'
                    : item.severity === 'major'
                    ? 'text-accent-disruption'
                    : 'text-text-muted'}`}
              >
                {KIND_ICON[item.kind]}
              </span>

              {/* Main content */}
              <div className="flex-1 min-w-0">
                {/* Headline row */}
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm text-text-primary font-medium leading-snug">
                    {item.headline}
                  </span>
                  <SeverityBadge severity={item.severity} />
                </div>

                {/* Stake row — the money / hours line */}
                <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                  <span className="text-xs text-accent-disruption tabular-nums font-medium">
                    {item.stake}
                  </span>
                  <span className="text-[10px] text-text-muted tabular-nums">
                    {formatDistanceToNow(new Date(item.updatedAt), { addSuffix: true })}
                  </span>
                </div>
              </div>

              {/* Arrow — only visible on hover/focus */}
              <span
                className="text-text-muted text-xs shrink-0 pt-0.5 opacity-0 group-hover:opacity-100 group-focus-visible:opacity-100 transition-opacity"
                aria-hidden="true"
              >
                →
              </span>
            </div>
          </button>
        </li>
      ))}
    </ol>
  );
}
