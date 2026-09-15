/**
 * DemoPanel.tsx — One-click demo entry.
 *
 * Shows the demo credentials as selectable text, and an "Enter demo" button
 * that calls onFill with the credentials. The parent form then submits.
 *
 * A judge must never have to create an account to see the product.
 */
import React from 'react';

interface DemoPanelProps {
  onFill: (email: string, password: string) => void;
  isLoading: boolean;
}

export const DEMO_EMAIL = 'demo@coldfront.app';
export const DEMO_PASSWORD = 'demo-control-tower';

export function DemoPanel({ onFill, isLoading }: DemoPanelProps) {
  return (
    <div
      className="rounded-lg p-4 mb-6"
      style={{
        background: '#ece8e2',
        border: '1px solid #d6d0c8',
      }}
    >
      <p className="text-xs font-semibold uppercase tracking-widest mb-2" style={{ color: '#6b6560' }}>
        Try the demo
      </p>
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="font-mono text-sm space-y-0.5" style={{ color: '#1a1814', fontFamily: "'IBM Plex Mono', monospace" }}>
          <div>
            <span style={{ color: '#6b6560', userSelect: 'none' }}>email  </span>
            <span style={{ userSelect: 'all' }}>{DEMO_EMAIL}</span>
          </div>
          <div>
            <span style={{ color: '#6b6560', userSelect: 'none' }}>passwd </span>
            <span style={{ userSelect: 'all' }}>{DEMO_PASSWORD}</span>
          </div>
        </div>
        <button
          type="button"
          onClick={() => onFill(DEMO_EMAIL, DEMO_PASSWORD)}
          disabled={isLoading}
          className="shrink-0 px-4 py-2 rounded text-sm font-medium transition-colors duration-75 outline-none focus-visible:ring-2 disabled:opacity-50"
          style={{
            background: '#1a1814',
            color: '#f5f2ee',
            minHeight: 44,
          }}
          onMouseOver={(e) => { (e.currentTarget as HTMLButtonElement).style.background = '#2d2926'; }}
          onMouseOut={(e) => { (e.currentTarget as HTMLButtonElement).style.background = '#1a1814'; }}
        >
          Enter demo →
        </button>
      </div>
    </div>
  );
}
