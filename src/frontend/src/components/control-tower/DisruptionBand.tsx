import React from 'react';
import { Link } from 'react-router-dom';
import { formatDistanceToNow } from 'date-fns';
import type { Disruption } from '@/types/domain';
import { SeverityBadge } from '@/components/ui/Badge';

interface DisruptionBandProps {
  disruptions: Disruption[];
}

const TYPE_LABEL: Record<string, string> = {
  weather: 'Weather',
  labour_action: 'Labour action',
  geopolitical: 'Geopolitical',
  congestion: 'Congestion',
  infrastructure: 'Infrastructure',
  customs: 'Customs',
};

export function DisruptionBand({ disruptions }: DisruptionBandProps) {
  if (disruptions.length === 0) return null;

  return (
    <div
      className="border-b border-surface-border bg-surface-raised/90 px-4 py-2 flex gap-3 overflow-x-auto shrink-0"
      role="region"
      aria-label="Active disruptions"
    >
      {disruptions.map((dis) => (
        <Link
          key={dis.id}
          to={`/disruptions/${dis.id}`}
          className="flex items-center gap-3 px-3 py-2 rounded border border-surface-border bg-surface-base
            hover:border-accent-disruption/50 hover:bg-surface-raised transition-colors duration-75
            focus-visible:ring-2 focus-visible:ring-accent-minor outline-none shrink-0 min-w-0"
          aria-label={`${dis.headline} — ${dis.severity} severity. Click for details.`}
        >
          <SeverityBadge severity={dis.severity} />
          <div className="min-w-0">
            <div className="text-sm font-medium text-text-primary truncate max-w-[280px]">
              {dis.headline}
            </div>
            <div className="flex items-center gap-2 text-xs text-text-muted mt-0.5">
              <span>{TYPE_LABEL[dis.type] ?? dis.type}</span>
              <span>·</span>
              <span>{formatDistanceToNow(new Date(dis.startedAt), { addSuffix: true })}</span>
              <span>·</span>
              <span className={dis.confidence < 0.6 ? 'text-accent-disruption' : ''}>
                {Math.round(dis.confidence * 100)}% confidence
                {dis.confidence < 0.6 && ' — unconfirmed'}
              </span>
            </div>
          </div>
          <span className="text-sm text-text-muted source-text hidden md:block shrink-0 ml-2 text-xs italic">
            {dis.source}
          </span>
        </Link>
      ))}
    </div>
  );
}
