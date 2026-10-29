import { useEffect, useRef } from 'react';

import { DataStatusBanner, Section } from '../../components/StateViews';
import { Badge, Eyebrow, Panel } from '../../components/ui';
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
    <section aria-labelledby="game-heading" className="space-y-4">
      <button
        ref={backRef}
        type="button"
        onClick={onBack}
        className="inline-flex items-center rounded-lg border border-white/10 bg-board-900/60 px-3 py-1.5 text-xs text-chalk-300 transition hover:border-white/20 hover:text-chalk-50"
      >
        ← Back to games
      </button>
      <Section state={state} loadingLabel="Loading game…">
        {({ game, pgn, ...meta }) => {
          const moves = pgn.moves_san ?? [];
          return (
            <div className="animate-rise space-y-4">
              <div className="flex flex-wrap items-end justify-between gap-3">
                <div>
                  <Eyebrow>Game detail</Eyebrow>
                  <h2
                    id="game-heading"
                    className="mt-1 font-display text-3xl tracking-tight text-chalk-50"
                  >
                    {OUTCOME_LABEL[game.result]} vs {game.opponent.username}
                  </h2>
                  <p className="mt-2 flex items-center gap-2 text-sm text-chalk-400">
                    <Badge tone={game.result}>{OUTCOME_LABEL[game.result]}</Badge>
                    {formatDateTime(game.played_at)}
                  </p>
                </div>
                {game.game_url && (
                  <a
                    href={game.game_url}
                    target="_blank"
                    rel="noreferrer"
                    className="rounded-lg border border-mint-400/30 bg-mint-400/10 px-3 py-1.5 text-xs font-medium text-mint-300 transition hover:bg-mint-400/20"
                  >
                    Open on Chess.com
                    <span aria-hidden="true" className="ml-1">
                      ↗
                    </span>
                  </a>
                )}
              </div>

              <DataStatusBanner meta={meta} />

              <div className="grid gap-3 lg:grid-cols-[0.85fr_1.15fr]">
                <Panel className="p-4 sm:p-5">
                  <h3 className="text-sm font-medium text-chalk-100">Game facts</h3>
                  <dl className="mt-4 space-y-3 text-sm">
                    <div className="flex items-baseline justify-between gap-3 border-b border-white/[0.05] pb-2.5">
                      <dt className="text-chalk-400">Ended</dt>
                      <dd className="text-right text-chalk-100">
                        {formatDateTime(game.played_at)}
                      </dd>
                    </div>
                    <div className="flex items-baseline justify-between gap-3 border-b border-white/[0.05] pb-2.5">
                      <dt className="text-chalk-400">Colour</dt>
                      <dd className="capitalize text-chalk-100">{game.color}</dd>
                    </div>
                    <div className="flex items-baseline justify-between gap-3 border-b border-white/[0.05] pb-2.5">
                      <dt className="text-chalk-400">Ratings reported with the game</dt>
                      <dd className="text-right tabular-nums text-chalk-100">
                        You {formatNumber(game.player_rating)} · Opponent{' '}
                        {formatNumber(game.opponent.rating)}
                      </dd>
                    </div>
                    <div className="flex items-baseline justify-between gap-3 border-b border-white/[0.05] pb-2.5">
                      <dt className="text-chalk-400">Time control</dt>
                      <dd className="tabular-nums text-chalk-100">
                        {game.time_control ?? MISSING}
                      </dd>
                    </div>
                    <div className="flex items-baseline justify-between gap-3 border-b border-white/[0.05] pb-2.5">
                      <dt className="text-chalk-400">Rated</dt>
                      <dd className="text-chalk-100">
                        {game.rated === null ? MISSING : game.rated ? 'Yes' : 'No'}
                      </dd>
                    </div>
                    <div className="flex items-baseline justify-between gap-3">
                      <dt className="text-chalk-400">Opening</dt>
                      <dd className="max-w-[60%] text-right text-chalk-100">
                        {game.opening
                          ? `${game.opening.name}${game.opening.eco_code ? ` (${game.opening.eco_code})` : ''}`
                          : 'Unknown opening'}
                      </dd>
                    </div>
                  </dl>
                </Panel>

                <Panel className="p-4 sm:p-5">
                  <div className="flex items-center justify-between gap-2">
                    <h3 className="text-sm font-medium text-chalk-100">Moves</h3>
                    {pgn.status === 'available' && moves.length > 0 && (
                      <span className="text-xs tabular-nums text-chalk-500">
                        {Math.ceil(moves.length / 2)} moves
                      </span>
                    )}
                  </div>
                  {pgn.status === 'available' && pgn.moves_san ? (
                    <ol className="mt-3 grid gap-x-6 gap-y-0.5 font-mono text-sm sm:grid-cols-2">
                      {moves.map((san, i) => {
                        if (i % 2 !== 0) return null;
                        const reply = moves[i + 1];
                        return (
                          <li
                            key={i}
                            className="rounded px-2 py-1 transition-colors hover:bg-white/[0.04]"
                          >
                            <span className="tabular-nums text-chalk-200">
                              {i / 2 + 1}. {san}
                              {reply ? ` ${reply}` : ''}
                            </span>
                          </li>
                        );
                      })}
                    </ol>
                  ) : (
                    <p className="mt-3 rounded-xl border border-dashed border-white/15 bg-board-900/40 p-3 text-sm text-chalk-400">
                      {pgn.status === 'missing'
                        ? 'Moves are not available for this game.'
                        : `The moves of this game could not be read (${pgn.error ?? 'unknown error'}).`}
                    </p>
                  )}
                </Panel>
              </div>
            </div>
          );
        }}
      </Section>
    </section>
  );
}
