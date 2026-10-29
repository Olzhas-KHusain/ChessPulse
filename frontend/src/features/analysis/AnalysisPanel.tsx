import { useEffect, useState } from 'react';

import { Badge, Eyebrow, Panel, type BadgeTone } from '../../components/ui';
import { ApiError, type ChesspulseApi } from '../../services/chesspulseApi';
import type { AnalysisState, MoveClassification } from '../../types/api';
import { formatNumber, MISSING } from '../../utils/format';

const CLASSIFICATION_TONE: Record<MoveClassification, BadgeTone> = {
  best: 'win',
  good: 'neutral',
  inaccuracy: 'unknown',
  mistake: 'draw',
  blunder: 'loss',
};

const CLASSIFICATION_LABEL: Record<MoveClassification, string> = {
  best: 'Best',
  good: 'Good',
  inaccuracy: 'Inaccuracy',
  mistake: 'Mistake',
  blunder: 'Blunder',
};

const FAILURE_MESSAGE: Record<string, string> = {
  missing_pgn: 'This game has no PGN, so the engine cannot review it.',
  malformed_pgn: 'The moves of this game could not be read, so it cannot be reviewed.',
  too_many_moves: 'This game is too long for the current analysis limit.',
  ENGINE_UNAVAILABLE: 'The analysis worker could not start the engine. Try again later.',
  ENGINE_TIMEOUT: 'The engine did not finish in time. Try again.',
  INTERNAL_ERROR: 'The analysis failed unexpectedly. Try again.',
};

const POLL_MS = 2500;

/**
 * Engine review of one game.
 *
 * The panel asks the API for a cached result on mount, requests one on demand and
 * polls while a background worker is running. Accuracy numbers are engine-derived
 * only; the copy says "mean move accuracy" and never calls them an Elo estimate.
 */
export function AnalysisPanel({
  api,
  username,
  gameId,
  playerColor,
}: {
  api: ChesspulseApi;
  username: string;
  gameId: string;
  playerColor: 'white' | 'black';
}) {
  const [state, setState] = useState<AnalysisState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [requesting, setRequesting] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    setState(null);
    setError(null);
    api.analysis(username, gameId, controller.signal).then(
      (next) => {
        if (!controller.signal.aborted) setState(next);
      },
      (cause: unknown) => {
        if (controller.signal.aborted) return;
        setError(cause instanceof ApiError ? cause.message : 'Could not check the analysis.');
      },
    );
    return () => controller.abort();
  }, [api, username, gameId]);

  useEffect(() => {
    if (state?.status !== 'queued' && state?.status !== 'running') return undefined;
    const timer = setInterval(() => {
      api.analysis(username, gameId).then(setState, () => undefined);
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [api, username, gameId, state?.status]);

  async function request() {
    setRequesting(true);
    setError(null);
    try {
      setState(await api.requestAnalysis(username, gameId));
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'The analysis could not be requested.');
    } finally {
      setRequesting(false);
    }
  }

  if (error !== null) {
    return (
      <Panel className="p-4 sm:p-5">
        <Eyebrow>Engine review</Eyebrow>
        <p className="mt-2 text-sm text-coral-300">{error}</p>
        <button
          type="button"
          onClick={request}
          className="mt-3 rounded-lg border border-white/10 bg-board-900/60 px-3 py-1.5 text-xs text-chalk-200 transition hover:border-white/20 hover:text-chalk-50"
        >
          Try again
        </button>
      </Panel>
    );
  }

  if (state === null) {
    return (
      <Panel className="p-4 sm:p-5">
        <Eyebrow>Engine review</Eyebrow>
        <p className="mt-2 text-sm text-chalk-400">Checking for an existing analysis…</p>
      </Panel>
    );
  }

  if (state.status === 'missing' || state.status === 'failed') {
    return (
      <Panel className="p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <Eyebrow>Engine review</Eyebrow>
            <h3 className="mt-1 font-display text-xl tracking-tight text-chalk-50">
              Stockfish, move by move
            </h3>
            <p className="mt-2 max-w-xl text-sm leading-relaxed text-chalk-400">
              A background worker evaluates every position, then reports accuracy, average centipawn
              loss and the moves that cost the most. It runs once per game and is cached.
            </p>
          </div>
          <button
            type="button"
            onClick={request}
            disabled={requesting}
            className="rounded-xl bg-mint-400 px-4 py-2 text-sm font-semibold text-board-950 shadow-[0_8px_24px_-10px] shadow-mint-400/80 transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {requesting ? 'Requesting…' : 'Analyze with Stockfish'}
          </button>
        </div>
        {state.status === 'failed' && (
          <p className="mt-3 rounded-xl border border-coral-400/25 bg-coral-400/10 p-3 text-sm text-coral-200">
            {FAILURE_MESSAGE[state.error_code ?? ''] ??
              `The analysis failed (${state.error_code ?? 'unknown error'}).`}
          </p>
        )}
      </Panel>
    );
  }

  if (state.status === 'queued' || state.status === 'running') {
    return (
      <Panel className="p-4 sm:p-5">
        <Eyebrow>Engine review</Eyebrow>
        <p className="mt-2 flex items-center gap-2 text-sm text-chalk-300">
          <span
            aria-hidden="true"
            className="h-2 w-2 animate-pulse rounded-full bg-mint-400 shadow-[0_0_10px] shadow-mint-400"
          />
          {state.status === 'queued'
            ? 'Queued for the analysis worker…'
            : 'Stockfish is reviewing this game…'}
        </p>
        <p className="mt-1 text-xs text-chalk-500">
          This page updates itself; you can keep browsing other games.
        </p>
      </Panel>
    );
  }

  const analysis = state.analysis;
  if (analysis === null) {
    return (
      <Panel className="p-4 sm:p-5">
        <p className="text-sm text-chalk-400">The analysis result is unavailable.</p>
      </Panel>
    );
  }

  const own = analysis.summary[playerColor];
  const rival = analysis.summary[playerColor === 'white' ? 'black' : 'white'];
  const moments = analysis.moves.filter(
    (move) =>
      move.color === playerColor &&
      (move.classification === 'blunder' ||
        move.classification === 'mistake' ||
        move.classification === 'inaccuracy'),
  );

  return (
    <Panel className="p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Eyebrow>Engine review</Eyebrow>
          <h3 className="mt-1 font-display text-xl tracking-tight text-chalk-50">
            Accuracy and key moments
          </h3>
        </div>
        <p className="text-xs text-chalk-500">
          {analysis.engine.name} {analysis.engine.version} · depth {analysis.engine.depth}
        </p>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Your accuracy" value={accuracy(own.accuracy)} />
        <Stat label="Opponent accuracy" value={accuracy(rival.accuracy)} />
        <Stat label="Your average centipawn loss" value={formatNumber(own.acpl)} />
        <Stat
          label="Your blunders · mistakes"
          value={`${own.counts.blunder} · ${own.counts.mistake}`}
        />
      </div>

      <div className="mt-5">
        <h4 className="text-sm font-medium text-chalk-100">Key moments</h4>
        {moments.length === 0 ? (
          <p className="mt-2 rounded-xl border border-dashed border-white/15 bg-board-900/40 p-3 text-sm text-chalk-400">
            No inaccuracies, mistakes or blunders were found in your moves.
          </p>
        ) : (
          <ol className="mt-2 divide-y divide-white/[0.05]">
            {moments.slice(0, 8).map((move) => (
              <li
                key={move.ply}
                className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm"
              >
                <span className="flex items-center gap-2">
                  <span className="w-10 shrink-0 tabular-nums text-chalk-500">
                    {move.move_number}.
                  </span>
                  <span className="font-mono text-chalk-100">{move.san}</span>
                  <Badge tone={CLASSIFICATION_TONE[move.classification]}>
                    {CLASSIFICATION_LABEL[move.classification]}
                  </Badge>
                </span>
                <span className="text-xs text-chalk-400">
                  −{formatNumber(move.cp_loss)} cp
                  {move.best_move_san ? ` · best was ${move.best_move_san}` : ''}
                </span>
              </li>
            ))}
          </ol>
        )}
      </div>

      <p className="mt-4 text-[11px] leading-relaxed text-chalk-500">
        Accuracy is the mean per-move retention of the engine’s win probability, not a rating
        estimate. Labels use fixed centipawn-loss thresholds; engine scores are never exact.
      </p>
    </Panel>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-white/[0.06] bg-white/[0.015] p-3">
      <p className="text-[10px] uppercase tracking-[0.16em] text-chalk-500">{label}</p>
      <p className="mt-1 font-display text-2xl leading-none tabular-nums text-chalk-50">{value}</p>
    </div>
  );
}

function accuracy(value: number | null): string {
  return value === null ? MISSING : `${value.toFixed(1)}%`;
}
