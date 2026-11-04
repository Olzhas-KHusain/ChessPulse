import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApiError, chesspulseApi } from './chesspulseApi';

afterEach(() => vi.unstubAllGlobals());

function stubFetch(response: Response | Error) {
  // Return a fresh clone per call: a Response body can be read only once.
  const fetchMock = vi.fn(() =>
    response instanceof Error ? Promise.reject(response) : Promise.resolve(response.clone()),
  );
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

describe('chesspulseApi', () => {
  const scope = { timeClass: 'rapid' as const, days: 30 };

  it('builds encoded URLs with query parameters and skips empty values', async () => {
    const fetchMock = stubFetch(new Response(JSON.stringify({ items: [] }), { status: 200 }));
    await chesspulseApi.games('a_b', { cursor: null, result: 'win', limit: 5, scope });
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/players/a_b/games?result=win&limit=5&time_class=rapid&days=30',
      expect.objectContaining({ headers: { Accept: 'application/json' } }),
    );
    await chesspulseApi.game('a_b', 'live:1', scope);
    expect(fetchMock).toHaveBeenLastCalledWith(
      '/api/v1/players/a_b/games/live%3A1?time_class=rapid&days=30',
      expect.anything(),
    );
  });

  it('maps the error envelope and Retry-After', async () => {
    stubFetch(
      new Response(
        JSON.stringify({
          error: { code: 'UPSTREAM_RATE_LIMITED', message: 'Later.', request_id: 'r' },
        }),
        { status: 503, headers: { 'Retry-After': '120' } },
      ),
    );
    const error = await chesspulseApi.overview('x', scope).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 503,
      code: 'UPSTREAM_RATE_LIMITED',
      retryAfterSeconds: 120,
    });
  });

  it('reports network failures and non-JSON errors', async () => {
    stubFetch(new TypeError('Failed to fetch'));
    await expect(chesspulseApi.overview('x', scope)).rejects.toMatchObject({
      code: 'NETWORK_ERROR',
    });
    stubFetch(new Response('<html>', { status: 500 }));
    await expect(chesspulseApi.overview('x', scope)).rejects.toMatchObject({
      status: 500,
      code: 'UNEXPECTED_ERROR',
    });
  });
});
