import { useId, useState } from 'react';

import { DataStatusBanner, EmptyNotice, Section } from '../../components/StateViews';
import { useApi } from '../../hooks/useApi';
import type { ChesspulseApi } from '../../services/chesspulseApi';
import type { GameSummary, PlayerOutcome } from '../../types/api';
import { formatDateTime, formatNumber, MISSING, OUTCOME_LABEL } from '../../utils/format';

const PAGE_SIZE = 20;

export function GamesPanel({
  api,
  username,
  onOpenGame,
}: {
  api: ChesspulseApi;
  username: string;
  onOpenGame: (gameId: string) => void;
}) {
  const [result, setResult] = useState<PlayerOutcome | null>(null);
  // cursors[i] is the cursor that loads page i (page 0 has none).
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
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

  return (
    <section aria-labelledby="games-heading" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="games-heading" className="text-lg font-semibold">
          Games
        </h2>
        <div className="flex items-center gap-2 text-sm">
          <label htmlFor={filterId}>Result</label>
          <select
            id={filterId}
            value={result ?? ''}
            onChange={(e) => changeFilter(e.target.value)}
            className="rounded border border-slate-300 px-2 py-1 focus-visible:ring-2 focus-visible:ring-indigo-600"
          >
            <option value="">All</option>
            <option value="win">Wins</option>
            <option value="loss">Losses</option>
            <option value="draw">Draws</option>
            <option value="unknown">Unknown</option>
          </select>
        </div>
      </div>
      <Section state={state} loadingLabel="Loading games…">
        {(data) => (
          <>
            <DataStatusBanner meta={data} />
            {data.items.length === 0 ? (
              <EmptyNotice>No games match this filter in the last 30 days.</EmptyNotice>
            ) : (
              <ul className="divide-y divide-slate-200 rounded-md border border-slate-200 bg-white">
                {data.items.map((g) => (
                  <GameRow key={g.game_id} game={g} onOpen={() => onOpenGame(g.game_id)} />
                ))}
              </ul>
            )}
            <nav aria-label="Game list pages" className="flex items-center justify-between gap-2">
              <button
                type="button"
                disabled={page === 0}
                onClick={() => setCursors((c) => c.slice(0, -1))}
                className="rounded border border-slate-300 px-3 py-1 disabled:opacity-40 focus-visible:ring-2 focus-visible:ring-indigo-600"
              >
                Previous page
              </button>
              <span className="text-sm text-slate-600">Page {page + 1}</span>
              <button
                type="button"
                disabled={data.next_cursor === null}
                onClick={() => setCursors((c) => [...c, data.next_cursor])}
                className="rounded border border-slate-300 px-3 py-1 disabled:opacity-40 focus-visible:ring-2 focus-visible:ring-indigo-600"
              >
                Next page
              </button>
            </nav>
          </>
        )}
      </Section>
    </section>
  );
}

const outcomeStyle: Record<PlayerOutcome, string> = {
  win: 'bg-green-100 text-green-900',
  loss: 'bg-red-100 text-red-900',
  draw: 'bg-slate-200 text-slate-900',
  unknown: 'bg-amber-100 text-amber-900',
};

function GameRow({ game, onOpen }: { game: GameSummary; onOpen: () => void }) {
  return (
    <li className="flex flex-col gap-1 p-3 sm:flex-row sm:items-center sm:justify-between">
      <div>
        {/* Outcome is shown as text, not by colour alone. */}
        <span
          className={`mr-2 rounded px-2 py-0.5 text-xs font-semibold ${outcomeStyle[game.result]}`}
        >
          {OUTCOME_LABEL[game.result]}
        </span>
        <span className="font-medium">vs {game.opponent.username}</span>
        <span className="ml-2 text-sm text-slate-600">
          ({formatNumber(game.opponent.rating)}) · {game.color} · {formatDateTime(game.played_at)}
        </span>
        <div className="text-sm text-slate-600">
          {game.opening ? game.opening.name : 'Unknown opening'} · {game.time_control ?? MISSING}
        </div>
      </div>
      <button
        type="button"
        onClick={onOpen}
        className="self-start rounded border border-indigo-300 px-3 py-1 text-sm text-indigo-800 focus-visible:ring-2 focus-visible:ring-indigo-600 sm:self-auto"
        aria-label={`Details of the game against ${game.opponent.username}, ${formatDateTime(game.played_at)}`}
      >
        Details
      </button>
    </li>
  );
}
