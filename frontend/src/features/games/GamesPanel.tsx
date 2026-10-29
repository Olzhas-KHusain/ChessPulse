import { useId, useState } from 'react';

import { DataStatusBanner, EmptyNotice, Section } from '../../components/StateViews';
import { Badge, Eyebrow, Panel } from '../../components/ui';
import { useApi } from '../../hooks/useApi';
import type { ChesspulseApi } from '../../services/chesspulseApi';
import type { GameSummary, PlayerOutcome } from '../../types/api';
import { formatDateTime, formatNumber, MISSING, OUTCOME_LABEL } from '../../utils/format';
import { GameDetailPanel } from './GameDetailPanel';

const PAGE_SIZE = 20;

const ACCENT: Record<PlayerOutcome, string> = {
  win: 'bg-mint-400',
  loss: 'bg-coral-400',
  draw: 'bg-chalk-400',
  unknown: 'bg-gold-400',
};

export function GamesPanel({ api, username }: { api: ChesspulseApi; username: string }) {
  const [result, setResult] = useState<PlayerOutcome | null>(null);
  // cursors[i] is the cursor that loads page i (page 0 has none).
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  // Kept here (not in the parent) so that returning from the details view
  // preserves the current page and result filter.
  const [openGame, setOpenGame] = useState<string | null>(null);
  const page = cursors.length - 1;
  const cursor = cursors[page] ?? null;
  const filterId = useId();

  const state = useApi(`${username}|${result ?? ''}|${cursor ?? ''}`, (signal) =>
    api.games(username, { cursor, result, limit: PAGE_SIZE }, signal),
  );

  function changeFilter(value: string) {
    setResult(value === '' ? null : (value as PlayerOutcome));
    setCursors([null]);
  }

  if (openGame !== null) {
    return (
      <GameDetailPanel
        api={api}
        username={username}
        gameId={openGame}
        onBack={() => setOpenGame(null)}
      />
    );
  }

  return (
    <section aria-labelledby="games-heading" className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <Eyebrow>History</Eyebrow>
          <h2
            id="games-heading"
            className="mt-1 font-display text-2xl tracking-tight text-chalk-50"
          >
            Games
          </h2>
        </div>
        <div className="flex items-center gap-2 text-xs text-chalk-400">
          <label htmlFor={filterId}>Result</label>
          <div className="relative">
            <select
              id={filterId}
              value={result ?? ''}
              onChange={(e) => changeFilter(e.target.value)}
              className="appearance-none rounded-lg border border-white/10 bg-board-850 py-1.5 pl-3 pr-8 text-xs text-chalk-100"
            >
              <option value="">All</option>
              <option value="win">Wins</option>
              <option value="loss">Losses</option>
              <option value="draw">Draws</option>
              <option value="unknown">Unknown</option>
            </select>
            <span
              aria-hidden="true"
              className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-[10px] text-chalk-500"
            >
              ▾
            </span>
          </div>
        </div>
      </div>

      <Section state={state} loadingLabel="Loading games…">
        {(data) => (
          <div className="space-y-3">
            <DataStatusBanner meta={data} />
            {data.items.length === 0 ? (
              <EmptyNotice>No games match this filter in the last 30 days.</EmptyNotice>
            ) : (
              <Panel className="overflow-hidden">
                <ul className="divide-y divide-white/5">
                  {data.items.map((g) => (
                    <GameRow key={g.game_id} game={g} onOpen={() => setOpenGame(g.game_id)} />
                  ))}
                </ul>
              </Panel>
            )}
            <nav aria-label="Game list pages" className="flex items-center justify-between gap-2">
              <button
                type="button"
                disabled={page === 0}
                onClick={() => setCursors((c) => c.slice(0, -1))}
                className="rounded-lg border border-white/10 bg-board-900/60 px-3 py-1.5 text-xs text-chalk-300 transition hover:border-white/20 hover:text-chalk-50 disabled:cursor-not-allowed disabled:opacity-30"
              >
                <span aria-hidden="true" className="mr-1">
                  ←
                </span>
                Previous page
              </button>
              <span className="text-xs tabular-nums text-chalk-500">Page {page + 1}</span>
              <button
                type="button"
                disabled={data.next_cursor === null}
                onClick={() => setCursors((c) => [...c, data.next_cursor])}
                className="rounded-lg border border-white/10 bg-board-900/60 px-3 py-1.5 text-xs text-chalk-300 transition hover:border-white/20 hover:text-chalk-50 disabled:cursor-not-allowed disabled:opacity-30"
              >
                Next page
                <span aria-hidden="true" className="ml-1">
                  →
                </span>
              </button>
            </nav>
          </div>
        )}
      </Section>
    </section>
  );
}

function GameRow({ game, onOpen }: { game: GameSummary; onOpen: () => void }) {
  return (
    <li className="flex flex-col gap-3 p-4 transition-colors hover:bg-white/[0.025] sm:flex-row sm:items-center sm:justify-between">
      <div className="flex min-w-0 items-start gap-3">
        <span
          aria-hidden="true"
          className={`mt-0.5 h-10 w-1 shrink-0 rounded-full ${ACCENT[game.result]}`}
        />
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            {/* Outcome is shown as text, not by colour alone. */}
            <Badge tone={game.result}>{OUTCOME_LABEL[game.result]}</Badge>
            <span className="font-medium text-chalk-50">vs {game.opponent.username}</span>
            <span className="text-xs text-chalk-400">
              ({formatNumber(game.opponent.rating)}) · {game.color} ·{' '}
              {formatDateTime(game.played_at)}
            </span>
          </div>
          <p className="mt-1 truncate text-sm text-chalk-300">
            {game.opening ? game.opening.name : 'Unknown opening'}
            <span className="mx-1.5 text-chalk-500">·</span>
            <span className="tabular-nums">{game.time_control ?? MISSING}</span>
          </p>
        </div>
      </div>
      <button
        type="button"
        onClick={onOpen}
        className="inline-flex shrink-0 items-center gap-1.5 self-start rounded-lg border border-white/10 bg-board-850 px-3 py-1.5 text-xs font-medium text-chalk-100 transition hover:border-mint-400/40 hover:text-mint-300 sm:self-auto"
        aria-label={`Details of the game against ${game.opponent.username}, ${formatDateTime(game.played_at)}`}
      >
        Details
        <span aria-hidden="true">→</span>
      </button>
    </li>
  );
}
