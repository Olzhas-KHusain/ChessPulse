import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { App } from './App';
import { ApiError, type ChesspulseApi } from './services/chesspulseApi';
import * as fx from './test/fixtures';

// Recharts needs real layout (ResizeObserver); the chart itself is not under test here.
vi.mock('recharts', async () => {
  const actual = await vi.importActual<typeof import('recharts')>('recharts');
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
      <div data-testid="rating-chart">{children}</div>
    ),
  };
});

afterEach(cleanup);

function fakeApi(overrides: Partial<ChesspulseApi> = {}): ChesspulseApi {
  return {
    overview: vi.fn().mockResolvedValue(fx.overview),
    ratingHistory: vi.fn().mockResolvedValue(fx.ratingHistory),
    openings: vi.fn().mockResolvedValue(fx.openings),
    opponents: vi.fn().mockResolvedValue(fx.opponents),
    games: vi.fn().mockResolvedValue(fx.gameList([1, 2], null)),
    game: vi.fn().mockResolvedValue(fx.gameDetail(1, 'available')),
    analysis: vi.fn().mockResolvedValue(fx.missingAnalysis),
    requestAnalysis: vi.fn().mockResolvedValue(fx.missingAnalysis),
    ...overrides,
  };
}

function search(username: string) {
  fireEvent.change(screen.getByLabelText('Chess.com username'), { target: { value: username } });
  fireEvent.click(screen.getByRole('button', { name: 'Analyze' }));
}

function metric(label: string): HTMLElement {
  const term = screen.getByText(label, { selector: 'dt' });
  const value = term.nextElementSibling;
  if (!(value instanceof HTMLElement)) throw new Error(`no value for ${label}`);
  return value;
}

describe('search', () => {
  it('loads and shows the overview for a valid username', async () => {
    const api = fakeApi();
    render(<App api={api} />);
    search('  Example_Player ');

    expect(screen.getByRole('status').textContent).toContain('Loading');
    expect(await screen.findByRole('heading', { name: 'example_player' })).toBeTruthy();
    expect(api.overview).toHaveBeenCalledWith('example_player', expect.anything());
    expect(metric('Games').textContent).toBe('42');
    expect(metric('Win rate').textContent).toBe('52.38%');
    expect(metric('Current Rapid rating').textContent).toBe('1,523');
    expect(metric('Current streak').textContent).toBe('3 wins');
    expect(metric('Longest winning streak').textContent).toBe('5');
  });

  it.each(['', 'bad name', 'a/b', 'é'])(
    'rejects invalid input %j without calling the API',
    (value) => {
      const api = fakeApi();
      render(<App api={api} />);
      search(value);
      expect(screen.getByRole('alert').textContent).toMatch(/username|letters/i);
      expect(screen.getByLabelText('Chess.com username').getAttribute('aria-invalid')).toBe('true');
      expect(api.overview).not.toHaveBeenCalled();
    },
  );

  it('explains a player that does not exist', async () => {
    const api = fakeApi({
      overview: vi.fn().mockRejectedValue(new ApiError(404, 'PLAYER_NOT_FOUND', 'x', null)),
    });
    render(<App api={api} />);
    search('nobody');
    expect((await screen.findByRole('alert')).textContent).toContain('No Chess.com player');
  });

  it('explains a provider outage without cached data', async () => {
    const api = fakeApi({
      overview: vi.fn().mockRejectedValue(new ApiError(503, 'UPSTREAM_UNAVAILABLE', 'x', 300)),
    });
    render(<App api={api} />);
    search('example_player');
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('temporarily unavailable');
    expect(alert.textContent).toContain('300 s');
  });
});

describe('overview states', () => {
  it('shows an empty period with dashes, never zero win rate or rating', async () => {
    render(<App api={fakeApi({ overview: vi.fn().mockResolvedValue(fx.emptyOverview) })} />);
    search('example_player');
    expect(await screen.findByText('No eligible Rapid games in the last 30 days.')).toBeTruthy();
    for (const label of [
      'Win rate',
      'Current Rapid rating',
      'Current streak',
      'Longest winning streak',
    ]) {
      expect(metric(label).textContent).toContain('—');
      expect(metric(label).textContent).toContain('not available');
      expect(metric(label).textContent).not.toContain('0');
    }
  });

  it('marks stale data with the last successful update', async () => {
    const stale = {
      ...fx.overview,
      data_status: 'stale' as const,
      refresh_error: 'UPSTREAM_TIMEOUT',
    };
    render(<App api={fakeApi({ overview: vi.fn().mockResolvedValue(stale) })} />);
    search('example_player');
    const banner = await screen.findByTestId('data-status-banner');
    expect(banner.textContent).toContain('Showing saved data');
    expect(banner.textContent).toContain('UPSTREAM_TIMEOUT');
  });

  it('marks partial data and incomplete streaks', async () => {
    const partial = {
      ...fx.overview,
      data_status: 'partial' as const,
      refresh_error: 'INGESTION_INCOMPLETE',
      streak_may_be_incomplete: true,
    };
    render(<App api={fakeApi({ overview: vi.fn().mockResolvedValue(partial) })} />);
    search('example_player');
    expect((await screen.findByTestId('data-status-banner')).textContent).toContain(
      'may be incomplete',
    );
    expect(screen.getByText(/Streaks may not reflect every game/)).toBeTruthy();
  });
});

async function openTab(name: string) {
  fireEvent.click(await screen.findByRole('tab', { name }));
}

describe('sections', () => {
  it('draws the rating chart only when observations exist', async () => {
    const api = fakeApi();
    render(<App api={api} />);
    search('example_player');
    await openTab('Rating history');
    expect(await screen.findByTestId('rating-chart')).toBeTruthy();
    cleanup();

    render(
      <App api={fakeApi({ ratingHistory: vi.fn().mockResolvedValue(fx.emptyRatingHistory) })} />,
    );
    search('example_player');
    await openTab('Rating history');
    expect(
      await screen.findByText('No rating observations are available for this period.'),
    ).toBeTruthy();
    expect(screen.queryByTestId('rating-chart')).toBeNull();
  });

  it('shows openings with sample sizes and an honest unknown group', async () => {
    render(<App api={fakeApi()} />);
    search('example_player');
    await openTab('Openings');
    const table = await screen.findByRole('table');
    expect(within(table).getByText('Sicilian Defense')).toBeTruthy();
    expect(within(table).getByText('Unknown opening')).toBeTruthy();
    expect(within(table).getByText('66.67%')).toBeTruthy();
  });

  it('a failing section does not hide the overview', async () => {
    const api = fakeApi({
      opponents: vi.fn().mockRejectedValue(new ApiError(504, 'UPSTREAM_TIMEOUT', 'x', null)),
    });
    render(<App api={api} />);
    search('example_player');
    await openTab('Opponents');
    expect((await screen.findByRole('alert')).textContent).toContain('temporarily unavailable');
    await openTab('Overview');
    expect(metric('Games').textContent).toBe('42');
  });

  it('supports keyboard navigation between tabs', async () => {
    render(<App api={fakeApi()} />);
    search('example_player');
    const overviewTab = await screen.findByRole('tab', { name: 'Overview' });
    fireEvent.keyDown(overviewTab, { key: 'ArrowRight' });
    const ratingTab = screen.getByRole('tab', { name: 'Rating history' });
    expect(ratingTab.getAttribute('aria-selected')).toBe('true');
    expect(document.activeElement).toBe(ratingTab);
  });
});

describe('games', () => {
  it('paginates with cursors and opens game details', async () => {
    const games = vi
      .fn()
      .mockImplementation((_u: string, opts: { cursor: string | null }) =>
        Promise.resolve(opts.cursor === 'c2' ? fx.gameList([3], null) : fx.gameList([1, 2], 'c2')),
      );
    const game = vi.fn().mockResolvedValue(fx.gameDetail(3, 'available'));
    render(<App api={fakeApi({ games, game })} />);
    search('example_player');
    await openTab('Games');

    expect(await screen.findByText('vs rival_1')).toBeTruthy();
    const previous = screen.getByRole('button', { name: 'Previous page' }) as HTMLButtonElement;
    expect(previous.disabled).toBe(true);

    fireEvent.click(screen.getByRole('button', { name: 'Next page' }));
    expect(await screen.findByText('vs rival_3')).toBeTruthy();
    expect(games).toHaveBeenLastCalledWith(
      'example_player',
      expect.objectContaining({ cursor: 'c2' }),
      expect.anything(),
    );
    expect((screen.getByRole('button', { name: 'Next page' }) as HTMLButtonElement).disabled).toBe(
      true,
    );

    fireEvent.click(screen.getByRole('button', { name: /Details of the game against rival_3/ }));
    expect(await screen.findByText('1. e4 e5')).toBeTruthy();
    expect(game).toHaveBeenCalledWith('example_player', 'live:3', expect.anything());

    fireEvent.click(screen.getByRole('button', { name: '← Back to games' }));
    expect(await screen.findByText('vs rival_3')).toBeTruthy();
  });

  it('applies the result filter from the first page', async () => {
    const games = vi.fn().mockResolvedValue(fx.gameList([], null));
    render(<App api={fakeApi({ games })} />);
    search('example_player');
    await openTab('Games');
    fireEvent.change(await screen.findByLabelText('Result'), { target: { value: 'loss' } });
    await waitFor(() =>
      expect(games).toHaveBeenLastCalledWith(
        'example_player',
        expect.objectContaining({ result: 'loss', cursor: null }),
        expect.anything(),
      ),
    );
    expect(await screen.findByText('No games match this filter in the last 30 days.')).toBeTruthy();
  });

  it.each([
    ['missing', 'Moves are not available for this game.'],
    ['malformed', 'could not be read (illegal_move)'],
  ] as const)('handles %s PGN in details', async (status, text) => {
    render(<App api={fakeApi({ game: vi.fn().mockResolvedValue(fx.gameDetail(1, status)) })} />);
    search('example_player');
    await openTab('Games');
    fireEvent.click(
      await screen.findByRole('button', { name: /Details of the game against rival_1/ }),
    );
    expect(await screen.findByText(new RegExp(text.replace(/[()]/g, '\\$&')))).toBeTruthy();
  });

  it('requests engine analysis and shows accuracy with key moments', async () => {
    const requestAnalysis = vi.fn().mockResolvedValue(fx.completedAnalysis());
    render(
      <App
        api={fakeApi({
          analysis: vi.fn().mockResolvedValue(fx.missingAnalysis),
          requestAnalysis,
        })}
      />,
    );
    search('example_player');
    await openTab('Games');
    fireEvent.click(
      await screen.findByRole('button', { name: /Details of the game against rival_1/ }),
    );

    fireEvent.click(await screen.findByRole('button', { name: 'Analyze with Stockfish' }));

    expect(await screen.findByText('Accuracy and key moments')).toBeTruthy();
    expect(screen.getByText('84.0%')).toBeTruthy();
    expect(screen.getByText('90.0%')).toBeTruthy();
    expect(screen.getByText('Nf3')).toBeTruthy();
    expect(screen.getByText(/best was Bc4/)).toBeTruthy();
    expect(requestAnalysis).toHaveBeenCalledWith('example_player', 'live:1');
  });
});
