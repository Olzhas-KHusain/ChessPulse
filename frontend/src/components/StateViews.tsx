import type { ReactNode } from 'react';

import type { ApiState } from '../hooks/useApi';
import { ApiError } from '../services/chesspulseApi';
import type { DatasetMeta } from '../types/api';
import { formatDateTime } from '../utils/format';

function errorMessage(error: ApiError): string {
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
    <div
      role="status"
      aria-live="polite"
      className="flex items-center gap-3 rounded-2xl border border-white/[0.07] bg-board-900/60 px-4 py-3 text-sm text-chalk-300"
    >
      <span aria-hidden="true" className="relative flex h-3.5 w-3.5">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-mint-400/40" />
        <span className="relative inline-flex h-3.5 w-3.5 rounded-full bg-mint-400" />
      </span>
      {label}
    </div>
  );
}

export function ErrorNotice({ error }: { error: ApiError }) {
  return (
    <div
      role="alert"
      className="rounded-2xl border border-coral-400/30 bg-coral-400/[0.08] p-4 text-coral-300"
    >
      <p className="flex items-start gap-2 font-medium">
        <span
          aria-hidden="true"
          className="mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full bg-coral-400/20 text-[10px] font-bold"
        >
          !
        </span>
        {errorMessage(error)}
      </p>
      <p className="mt-2 pl-6 text-xs text-coral-300/70">Error code: {error.code}</p>
    </div>
  );
}

export function EmptyNotice({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-2xl border border-dashed border-white/15 bg-board-900/40 p-4 text-sm text-chalk-400">
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
    return (
      <p className="flex items-center gap-2 text-xs text-chalk-500">
        <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-mint-400" />
        Data updated {updated}.
      </p>
    );
  }
  const stale = meta.data_status === 'stale';
  return (
    <div
      role="status"
      className="rounded-xl border border-gold-400/30 bg-gold-400/10 p-3 text-sm text-gold-300"
      data-testid="data-status-banner"
    >
      <p className="flex items-start gap-2 font-medium">
        <span
          aria-hidden="true"
          className="mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full bg-gold-400/20 text-[10px] font-bold"
        >
          !
        </span>
        {stale
          ? `Showing saved data from ${updated}: the latest update from Chess.com failed.`
          : 'Some of this player’s games could not be loaded; results may be incomplete.'}
      </p>
      {meta.refresh_error && (
        <p className="mt-1 pl-6 text-xs text-gold-300/70">Reason: {meta.refresh_error}</p>
      )}
    </div>
  );
}
