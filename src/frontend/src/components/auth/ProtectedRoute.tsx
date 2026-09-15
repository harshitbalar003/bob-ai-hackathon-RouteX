/**
 * ProtectedRoute.tsx — Wraps gated routes.
 *
 * While status === 'loading': renders an app-shell skeleton (no redirect).
 * While status === 'anon':    redirects to /login?returnTo=<current path>.
 * While status === 'authed':  renders children via <Outlet />.
 *
 * The loading skeleton prevents the race condition where a page refresh
 * redirects authenticated users to /login before /me has resolved.
 */
import React from 'react';
import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';

function AppShellSkeleton() {
  return (
    <div className="min-h-screen bg-surface-base flex flex-col">
      {/* Header skeleton */}
      <div className="h-11 border-b border-surface-border bg-surface-raised/80 flex items-center px-4 gap-6">
        <div className="w-24 h-4 bg-surface-2 rounded animate-pulse" />
        <div className="flex gap-1">
          {[80, 64, 56, 72].map((w, i) => (
            <div key={i} className={`h-6 rounded bg-surface-2 animate-pulse`} style={{ width: w }} />
          ))}
        </div>
      </div>
      {/* Content skeleton */}
      <main className="flex-1 p-6 space-y-4">
        <div className="h-6 w-48 bg-surface-2 rounded animate-pulse" />
        <div className="h-40 bg-surface-2 rounded animate-pulse" />
        <div className="h-24 bg-surface-2 rounded animate-pulse" />
      </main>
    </div>
  );
}

export function ProtectedRoute() {
  const { status } = useAuth();
  const location = useLocation();

  if (status === 'loading') {
    return <AppShellSkeleton />;
  }

  if (status === 'anon') {
    // Validate returnTo is a relative path before storing it
    const returnTo = location.pathname + location.search;
    const safeReturn = returnTo.startsWith('/') && !returnTo.startsWith('//') ? returnTo : '/tower';
    return <Navigate to={`/login?returnTo=${encodeURIComponent(safeReturn)}`} replace />;
  }

  return <Outlet />;
}
