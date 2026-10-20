/** Display helpers. Missing values render as an explicit dash, never as 0. */

export const MISSING = '—';

export function formatNumber(value: number | null | undefined): string {
  return value === null || value === undefined ? MISSING : value.toLocaleString('en-US');
}

export function formatPercent(value: number | null | undefined): string {
  return value === null || value === undefined ? MISSING : `${value.toFixed(2)}%`;
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return MISSING;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return MISSING;
  return date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

export function formatDate(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? MISSING
    : date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

const USERNAME_RE = /^[A-Za-z0-9_-]{1,64}$/;

/** Mirrors the backend rule (normalize_username): trimmed, 1-64 of A-Z a-z 0-9 _ -. */
export function validateUsername(
  raw: string,
): { ok: true; value: string } | { ok: false; message: string } {
  const value = raw.trim();
  if (value.length === 0) return { ok: false, message: 'Enter a Chess.com username.' };
  if (value.length > 64) return { ok: false, message: 'Usernames are at most 64 characters.' };
  if (!USERNAME_RE.test(value)) {
    return { ok: false, message: 'Use only letters, digits, underscores (_) or hyphens (-).' };
  }
  return { ok: true, value: value.toLowerCase() };
}

export const OUTCOME_LABEL: Record<'win' | 'loss' | 'draw' | 'unknown', string> = {
  win: 'Win',
  loss: 'Loss',
  draw: 'Draw',
  unknown: 'Unknown',
};
