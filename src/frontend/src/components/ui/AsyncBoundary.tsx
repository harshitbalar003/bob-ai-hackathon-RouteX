import React from 'react';

interface AsyncBoundaryProps<T> {
  data: T | undefined;
  isLoading: boolean;
  isError: boolean;
  error?: Error | null;
  isEmpty?: (data: T) => boolean;
  isStale?: boolean;
  staleThresholdMs?: number;
  dataUpdatedAt?: number;
  onRetry?: () => void;
  loadingFallback: React.ReactNode;
  emptyFallback: React.ReactNode;
  children: (data: T) => React.ReactNode;
}

/**
 * Renders one of four states: loading, error, empty, or populated (with stale
 * warning). Every async surface in the app should use this wrapper.
 */
export function AsyncBoundary<T>({
  data,
  isLoading,
  isError,
  error,
  isEmpty,
  isStale,
  dataUpdatedAt,
  onRetry,
  loadingFallback,
  emptyFallback,
  children,
}: AsyncBoundaryProps<T>) {
  if (isLoading) return <>{loadingFallback}</>;

  if (isError) {
    return (
      <div
        role="alert"
        className="p-4 rounded bg-accent-critical/10 border border-accent-critical/30 text-sm"
      >
        <p className="font-medium text-accent-critical mb-1">Failed to load data</p>
        <p className="text-text-muted mb-3">
          {error?.message ?? 'An unexpected error occurred.'}
        </p>
        {onRetry && (
          <button
            onClick={onRetry}
            className="text-sm text-text-primary underline underline-offset-2 hover:text-accent-minor focus-visible:ring-2 focus-visible:ring-accent-minor rounded outline-none"
          >
            Retry
          </button>
        )}
      </div>
    );
  }

  if (!data || (isEmpty && isEmpty(data))) {
    return <>{emptyFallback}</>;
  }

  return (
    <>
      {isStale && dataUpdatedAt && (
        <div className="px-3 py-1 text-xs text-text-muted border-b border-surface-border bg-surface-raised/50">
          Data last updated {new Date(dataUpdatedAt).toLocaleTimeString()} — may be stale
        </div>
      )}
      {children(data)}
    </>
  );
}
