import type { ReactNode } from 'react';

import type { ApiState } from '../hooks/useApi';
import { ApiError } from '../services/chesspulseApi';
import type { DatasetMeta } from '../types/api';
import { formatDateTime } from '../utils/format';

export function errorMessage(error: ApiError): string {
  switch (error.code) {
    case 'PLAYER_NOT_FOUND':
      return 'No Chess.com player with this username was found.';
    case 'GAME_NOT_FOUND':
      return 'This game is not among the player’s Rapid games of the last 30 days.';
    case 'INVALID_USERNAME':
    case 'INVALID_PARAMETER':
      return error.message;
    case 'NETWORK_ERROR':
      return 'The ChessPulse server could not be reached. Check your connection and try again.';
    case 'REFRESH_IN_PROGRESS':
      return 'This player’s data is being loaded. Please try again in a moment.';
    default:
      if (error.status === 502 || error.status === 503 || error.status === 504) {
        const wait =
          error.retryAfterSeconds !== null
            ? ` Try again in about ${error.retryAfterSeconds} s.`
            : '';
        return `Chess.com data is temporarily unavailable and no saved copy exists yet.${wait}`;
      }
      return 'Something went wrong while loading this section.';
  }
}

export function Loading({ label }: { label: string }) {
  return (
    <div role="status" aria-live="polite" className="flex items-center gap-2 py-6 text-slate-600">
      <span
        aria-hidden="true"
        className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-slate-700"
      />
      {label}
    </div>
  );
}

export function ErrorNotice({ error }: { error: ApiError }) {
  return (
    <div role="alert" className="rounded-md border border-red-300 bg-red-50 p-4 text-red-900">
      <p className="font-medium">{errorMessage(error)}</p>
      <p className="mt-1 text-xs text-red-800">Error code: {error.code}</p>
    </div>
  );
}

export function EmptyNotice({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-md border border-dashed border-slate-300 p-4 text-slate-600">
      {children}
    </p>
  );
}

/** Renders loading / error states and delegates success to `children`. */
export function Section<T>({
  state,
  loadingLabel,
  children,
}: {
  state: ApiState<T> | null;
  loadingLabel: string;
  children: (data: T) => ReactNode;
}) {
  if (state === null || state.status === 'loading') return <Loading label={loadingLabel} />;
  if (state.status === 'error') return <ErrorNotice error={state.error} />;
  return <>{children(state.data)}</>;
}

/** Explicit freshness indicator; stale and partial data are never shown silently. */
export function DataStatusBanner({ meta }: { meta: DatasetMeta }) {
  const updated = formatDateTime(meta.last_successful_update);
  if (meta.data_status === 'fresh') {
    return <p className="text-xs text-slate-500">Data updated {updated}.</p>;
  }
  const stale = meta.data_status === 'stale';
  return (
    <div
      role="status"
      className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900"
      data-testid="data-status-banner"
    >
      <p className="font-medium">
        {stale
          ? `Showing saved data from ${updated}: the latest update from Chess.com failed.`
          : 'Some of this player’s games could not be loaded; results may be incomplete.'}
      </p>
      {meta.refresh_error && <p className="mt-1 text-xs">Reason: {meta.refresh_error}</p>}
    </div>
  );
}
