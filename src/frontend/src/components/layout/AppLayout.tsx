import React from 'react';
import { Outlet, NavLink } from 'react-router-dom';
import { useExcursions } from '@/lib/queries';

/** Dev-only data mode indicator — shows MOCK or API in bottom-right corner. */
function DataModeIndicator() {
  const source = import.meta.env.VITE_DATA_SOURCE ?? 'mock';
  const isApi = source === 'api';
  return (
    <div
      className={`fixed bottom-3 right-3 z-50 px-2 py-0.5 rounded text-[10px] font-mono tracking-widest opacity-60 pointer-events-none select-none
        ${isApi ? 'bg-accent-track/20 text-accent-track border border-accent-track/30' : 'bg-surface-2 text-text-muted border border-border-subtle'}`}
      title={isApi ? 'Live API data (VITE_DATA_SOURCE=api)' : 'Fixture data (VITE_DATA_SOURCE=mock)'}
      aria-hidden="true"
    >
      {isApi ? 'API' : 'MOCK'}
    </div>
  );
}

const NAV_LINKS = [
  { to: '/', label: 'Control Tower', exact: true },
  { to: '/cold-chain', label: 'Cold Chain' },
  { to: '/fleet', label: 'Fleet' },
  { to: '/reroutes', label: 'Reroutes' },
];

function ExcursionCount() {
  const { data } = useExcursions();
  const openCritical = data?.filter((e) => e.endedAt === null && e.severity === 'critical').length ?? 0;
  return (
    <span
      aria-live="assertive"
      aria-atomic="true"
      aria-label={openCritical > 0 ? `${openCritical} open critical temperature breach` : ''}
      className={`tabular-nums text-xs font-medium px-1.5 py-0.5 rounded
        ${openCritical > 0 ? 'bg-accent-critical/20 text-accent-critical' : 'hidden'}`}
    >
      {openCritical > 0 ? openCritical : null}
    </span>
  );
}

export function AppLayout() {
  return (
    <div className="min-h-screen bg-surface-base flex flex-col">
      {/* Global nav — thin chrome */}
      <header className="h-11 border-b border-surface-border bg-surface-raised/80 backdrop-blur flex items-center px-4 gap-6 shrink-0 z-20">
        <span className="text-sm font-medium text-text-primary tracking-tight">
          Control Tower
        </span>
        <nav aria-label="Main navigation" className="flex items-center gap-1">
          {NAV_LINKS.map(({ to, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `px-3 py-1 rounded text-sm transition-colors duration-75 outline-none
                focus-visible:ring-2 focus-visible:ring-accent-minor
                ${isActive
                  ? 'text-text-primary bg-surface-border'
                  : 'text-text-muted hover:text-text-primary hover:bg-surface-raised'}`
              }
            >
              {label}
              {label === 'Cold Chain' && <ExcursionCount />}
            </NavLink>
          ))}
        </nav>
      </header>

      {/* Page content */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>

      <DataModeIndicator />
    </div>
  );
}
