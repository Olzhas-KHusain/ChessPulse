/**
 * The only module that talks to the backend. Components never call fetch directly.
 */
import type {
  AnalysisState,
  AnalyzeScope,
  ApiErrorBody,
  BoardEvaluation,
  BoardMoveAnalysis,
  FormReport,
  GameDetail,
  GameList,
  GroupSort,
  Openings,
  Opponents,
  Overview,
  PlayerOutcome,
  RatingHistory,
  Scope,
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

async function requestJson<T>(url: string, init: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, init);
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
  return requestJson<T>(url, {
    method,
    headers: { Accept: 'application/json' },
    signal,
  });
}

async function postJson<T>(path: string, payload: unknown, signal?: AbortSignal): Promise<T> {
  return requestJson<T>(`${BASE_URL}${path}`, {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  });
}

const player = (username: string): string => `/api/v1/players/${encodeURIComponent(username)}`;

const scopeParams = (scope: Scope) => ({ time_class: scope.timeClass, days: scope.days });

export const chesspulseApi = {
  overview: (username: string, scope: Scope, signal?: AbortSignal) =>
    getJson<Overview>(`${player(username)}/overview`, scopeParams(scope), signal),
  ratingHistory: (username: string, scope: Scope, signal?: AbortSignal) =>
    getJson<RatingHistory>(`${player(username)}/rating-history`, scopeParams(scope), signal),
  openings: (username: string, sort: GroupSort, scope: Scope, signal?: AbortSignal) =>
    getJson<Openings>(
      `${player(username)}/openings`,
      { sort, limit: 50, ...scopeParams(scope) },
      signal,
    ),
  opponents: (username: string, sort: GroupSort, scope: Scope, signal?: AbortSignal) =>
    getJson<Opponents>(
      `${player(username)}/opponents`,
      { sort, limit: 50, ...scopeParams(scope) },
      signal,
    ),
  games: (
    username: string,
    options: {
      cursor: string | null;
      result: PlayerOutcome | null;
      limit?: number;
      scope: Scope;
    },
    signal?: AbortSignal,
  ) =>
    getJson<GameList>(
      `${player(username)}/games`,
      {
        cursor: options.cursor,
        result: options.result,
        limit: options.limit ?? 20,
        ...scopeParams(options.scope),
      },
      signal,
    ),
  game: (username: string, gameId: string, scope: Scope, signal?: AbortSignal) =>
    getJson<GameDetail>(
      `${player(username)}/games/${encodeURIComponent(gameId)}`,
      scopeParams(scope),
      signal,
    ),
  analysis: (username: string, gameId: string, scope: Scope, signal?: AbortSignal) =>
    getJson<AnalysisState>(
      `${player(username)}/games/${encodeURIComponent(gameId)}/analysis`,
      scopeParams(scope),
      signal,
    ),
  requestAnalysis: (username: string, gameId: string, scope: Scope, signal?: AbortSignal) =>
    getJson<AnalysisState>(
      `${player(username)}/games/${encodeURIComponent(gameId)}/analysis`,
      scopeParams(scope),
      signal,
      'POST',
    ),
  form: (username: string, scope: Scope, signal?: AbortSignal) =>
    getJson<FormReport>(`${player(username)}/form`, scopeParams(scope), signal),
  analyzeForm: (username: string, scope: Scope, signal?: AbortSignal) =>
    getJson<AnalyzeScope>(`${player(username)}/form/analyze`, scopeParams(scope), signal, 'POST'),
  boardEvaluate: (fen: string, signal?: AbortSignal) =>
    postJson<BoardEvaluation>('/api/v1/board/evaluate', { fen }, signal),
  boardMove: (fen: string, moveUci: string, signal?: AbortSignal) =>
    postJson<BoardMoveAnalysis>('/api/v1/board/move', { fen, move_uci: moveUci }, signal),
};

export type ChesspulseApi = typeof chesspulseApi;
