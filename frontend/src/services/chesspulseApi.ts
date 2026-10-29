/**
 * The only module that talks to the backend. Components never call fetch directly.
 */
import type {
  AnalysisState,
  ApiErrorBody,
  GameDetail,
  GameList,
  GroupSort,
  Openings,
  Opponents,
  Overview,
  PlayerOutcome,
  RatingHistory,
} from '../types/api';

const BASE_URL: string = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '';

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly retryAfterSeconds: number | null;

  constructor(status: number, code: string, message: string, retryAfterSeconds: number | null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

function isErrorBody(value: unknown): value is ApiErrorBody {
  if (typeof value !== 'object' || value === null || !('error' in value)) return false;
  const error = (value as { error: unknown }).error;
  return (
    typeof error === 'object' &&
    error !== null &&
    typeof (error as { code?: unknown }).code === 'string' &&
    typeof (error as { message?: unknown }).message === 'string'
  );
}

type Params = Record<string, string | number | null | undefined>;

async function getJson<T>(
  path: string,
  params: Params = {},
  signal?: AbortSignal,
  method: 'GET' | 'POST' = 'GET',
): Promise<T> {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== '') query.set(key, String(value));
  }
  const url = `${BASE_URL}${path}${query.size > 0 ? `?${query.toString()}` : ''}`;

  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers: { Accept: 'application/json' },
      signal,
    });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause;
    throw new ApiError(0, 'NETWORK_ERROR', 'The ChessPulse server could not be reached.', null);
  }

  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (!response.ok) {
    const retryHeader = response.headers.get('Retry-After');
    const retryAfter =
      retryHeader !== null && /^\d+$/.test(retryHeader) ? Number(retryHeader) : null;
    if (isErrorBody(body)) {
      throw new ApiError(response.status, body.error.code, body.error.message, retryAfter);
    }
    throw new ApiError(
      response.status,
      'UNEXPECTED_ERROR',
      'Unexpected server response.',
      retryAfter,
    );
  }
  if (body === null) {
    throw new ApiError(
      response.status,
      'INVALID_RESPONSE',
      'The server returned invalid data.',
      null,
    );
  }
  return body as T;
}

const player = (username: string): string => `/api/v1/players/${encodeURIComponent(username)}`;

export const chesspulseApi = {
  overview: (username: string, signal?: AbortSignal) =>
    getJson<Overview>(`${player(username)}/overview`, {}, signal),
  ratingHistory: (username: string, signal?: AbortSignal) =>
    getJson<RatingHistory>(`${player(username)}/rating-history`, {}, signal),
  openings: (username: string, sort: GroupSort, signal?: AbortSignal) =>
    getJson<Openings>(`${player(username)}/openings`, { sort, limit: 50 }, signal),
  opponents: (username: string, sort: GroupSort, signal?: AbortSignal) =>
    getJson<Opponents>(`${player(username)}/opponents`, { sort, limit: 50 }, signal),
  games: (
    username: string,
    options: { cursor: string | null; result: PlayerOutcome | null; limit?: number },
    signal?: AbortSignal,
  ) =>
    getJson<GameList>(
      `${player(username)}/games`,
      { cursor: options.cursor, result: options.result, limit: options.limit ?? 20 },
      signal,
    ),
  game: (username: string, gameId: string, signal?: AbortSignal) =>
    getJson<GameDetail>(`${player(username)}/games/${encodeURIComponent(gameId)}`, {}, signal),
  analysis: (username: string, gameId: string, signal?: AbortSignal) =>
    getJson<AnalysisState>(
      `${player(username)}/games/${encodeURIComponent(gameId)}/analysis`,
      {},
      signal,
    ),
  requestAnalysis: (username: string, gameId: string, signal?: AbortSignal) =>
    getJson<AnalysisState>(
      `${player(username)}/games/${encodeURIComponent(gameId)}/analysis`,
      {},
      signal,
      'POST',
    ),
};

export type ChesspulseApi = typeof chesspulseApi;
