import { useEffect, useRef } from 'react';

import { DataStatusBanner, Section } from '../../components/StateViews';
import { useApi } from '../../hooks/useApi';
import type { ChesspulseApi } from '../../services/chesspulseApi';
import { formatDateTime, formatNumber, MISSING, OUTCOME_LABEL } from '../../utils/format';

export function GameDetailPanel({
  api,
  username,
  gameId,
  onBack,
}: {
  api: ChesspulseApi;
  username: string;
  gameId: string;
  onBack: () => void;
}) {
  const state = useApi(`${username}|${gameId}`, (signal) => api.game(username, gameId, signal));
  const backRef = useRef<HTMLButtonElement>(null);
  useEffect(() => backRef.current?.focus(), []);

  return (
    <section aria-labelledby="game-heading" className="space-y-3">
      <button
        ref={backRef}
        type="button"
        onClick={onBack}
        className="rounded border border-slate-300 px-3 py-1 text-sm focus-visible:ring-2 focus-visible:ring-indigo-600"
      >
        ← Back to games
      </button>
      <Section state={state} loadingLabel="Loading game…">
        {({ game, pgn, ...meta }) => (
          <>
            <DataStatusBanner meta={meta} />
            <h2 id="game-heading" className="text-lg font-semibold">
              {OUTCOME_LABEL[game.result]} vs {game.opponent.username}
            </h2>
            <dl className="grid grid-cols-1 gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
              <dt className="text-slate-600">Ended</dt>
              <dd>{formatDateTime(game.played_at)}</dd>
              <dt className="text-slate-600">Colour</dt>
              <dd className="capitalize">{game.color}</dd>
              <dt className="text-slate-600">Ratings reported with the game</dt>
              <dd>
                You {formatNumber(game.player_rating)} · Opponent{' '}
                {formatNumber(game.opponent.rating)}
              </dd>
              <dt className="text-slate-600">Time control</dt>
              <dd>{game.time_control ?? MISSING}</dd>
              <dt className="text-slate-600">Rated</dt>
              <dd>{game.rated === null ? MISSING : game.rated ? 'Yes' : 'No'}</dd>
              <dt className="text-slate-600">Opening</dt>
              <dd>
                {game.opening
                  ? `${game.opening.name}${game.opening.eco_code ? ` (${game.opening.eco_code})` : ''}`
                  : 'Unknown opening'}
              </dd>
            </dl>
            {game.game_url && (
              <a
                href={game.game_url}
                target="_blank"
                rel="noreferrer"
                className="text-indigo-700 underline"
              >
                Open on Chess.com
              </a>
            )}
            <div>
              <h3 className="font-medium">Moves</h3>
              {pgn.status === 'available' && pgn.moves_san ? (
                <ol className="mt-1 flex flex-wrap gap-x-3 gap-y-1 font-mono text-sm">
                  {pgn.moves_san.map((san, i) =>
                    i % 2 === 0 ? (
                      <li key={i}>
                        {i / 2 + 1}. {san} {pgn.moves_san?.[i + 1] ?? ''}
                      </li>
                    ) : null,
                  )}
                </ol>
              ) : (
                <p className="mt-1 text-sm text-slate-600">
                  {pgn.status === 'missing'
                    ? 'Moves are not available for this game.'
                    : `The moves of this game could not be read (${pgn.error ?? 'unknown error'}).`}
                </p>
              )}
            </div>
          </>
        )}
      </Section>
    </section>
  );
}
