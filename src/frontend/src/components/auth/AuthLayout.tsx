/**
 * AuthLayout.tsx — Shared split-panel layout for /login and /signup.
 *
 * Left side (form, 40% ≥ md): demo panel + auth form
 * Right side (product visual, 60% ≥ md): static temperature trace with excursion
 *
 * On mobile (<md): right panel collapses, form takes full width.
 *
 * An authenticated visit to /login or /signup redirects to /tower.
 */
import React from 'react';
import { Navigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { StaticExcursionTrace } from '@/components/auth/StaticExcursionTrace';

interface AuthLayoutProps {
  children: React.ReactNode;
}

export function AuthLayout({ children }: AuthLayoutProps) {
  const { status } = useAuth();
  const [searchParams] = useSearchParams();

  // If already authenticated, go to returnTo or /tower
  if (status === 'authed') {
    const returnTo = searchParams.get('returnTo');
    const safe = returnTo && returnTo.startsWith('/') && !returnTo.startsWith('//')
      ? returnTo
      : '/tower';
    return <Navigate to={safe} replace />;
  }

  // While loading auth, show nothing (prevents flash)
  if (status === 'loading') return null;

  return (
    <div className="min-h-screen flex" style={{ background: '#f5f2ee' }}>
      {/* ── Left: form panel ── */}
      <div
        className="flex flex-col justify-center w-full md:w-[42%] lg:w-[38%] px-6 sm:px-10 lg:px-14 py-10"
        style={{ background: '#f5f2ee' }}
      >
        {/* Brand */}
        <div className="mb-8">
          <a href="/" className="inline-flex items-baseline gap-2 group">
            <span
              className="text-xl font-semibold tracking-tight"
              style={{ color: '#1a1814' }}
            >
              Coldfront
            </span>
            <span className="text-xs" style={{ color: '#6b6560' }}>
              Supply Chain Control Tower
            </span>
          </a>
        </div>

        {/* Form content (LoginForm or SignupForm) */}
        {children}
      </div>

      {/* ── Right: product visual ── */}
      <div
        className="hidden md:flex flex-col flex-1 items-center justify-center p-8 lg:p-14"
        style={{ background: '#ece8e2', borderLeft: '1px solid #d6d0c8' }}
      >
        <div className="w-full max-w-xl">
          <StaticExcursionTrace />
        </div>
      </div>
    </div>
  );
}
