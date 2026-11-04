import { Badge, Eyebrow, Panel } from '../../components/ui';
import type { BoardEvaluation } from '../../types/api';
import { formatEvaluation, whiteShare } from './evaluation';
import { BOARD_STATUS_LABEL } from './labels';

interface EvaluationCardProps {
  evaluation: BoardEvaluation | null;
  busy: boolean;
  canPlayBest: boolean;
  onEvaluate: () => void;
  onPlayBest: () => void;
}

export function EvaluationCard({
  evaluation,
  busy,
  canPlayBest,
  onEvaluate,
  onPlayBest,
}: EvaluationCardProps) {
  const share = evaluation === null ? 50 : whiteShare(evaluation.eval_cp, evaluation.mate);
  const score = evaluation === null ? '—' : formatEvaluation(evaluation.eval_cp, evaluation.mate);

  return (
    <Panel className="p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Eyebrow>Engine verdict</Eyebrow>
          <h2 className="mt-1 font-display text-2xl tracking-tight text-chalk-50">Evaluation</h2>
        </div>
        <button
          type="button"
          onClick={onEvaluate}
          disabled={busy}
          className="rounded-xl bg-mint-400 px-4 py-2 text-sm font-semibold text-on-accent shadow-[0_8px_24px_-10px] shadow-mint-400/80 transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {busy ? 'Analysing…' : 'Evaluate position'}
        </button>
      </div>

      <div className="mt-4">
        <div
          role="img"
          aria-label={`Evaluation bar: ${score} from White's perspective`}
          className="flex h-3 overflow-hidden rounded-full border border-white/10 bg-eval-black"
        >
          <span
            className="h-full bg-eval-white transition-[width] duration-300"
            style={{ width: `${share}%` }}
          />
        </div>
        <div className="mt-2 flex items-center justify-between text-xs text-chalk-500">
          <span>White</span>
          <span className="font-mono text-sm font-semibold tabular-nums text-chalk-100">
            {score}
          </span>
          <span>Black</span>
        </div>
      </div>

      {evaluation === null ? (
        <p className="mt-4 text-sm leading-relaxed text-chalk-400">
          Run the engine on the current position. Scores are always shown from White’s perspective.
        </p>
      ) : (
        <div className="mt-4 space-y-3">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <Badge tone={evaluation.status === 'ongoing' ? 'neutral' : 'unknown'}>
              {BOARD_STATUS_LABEL[evaluation.status]}
            </Badge>
            <span className="text-chalk-400">
              {evaluation.turn === 'white' ? 'White' : 'Black'} to move
            </span>
          </div>

          <div className="rounded-xl border border-white/[0.06] bg-white/[0.015] p-3">
            <p className="text-[10px] uppercase tracking-[0.16em] text-chalk-500">
              Engine suggestion
            </p>
            <div className="mt-1 flex flex-wrap items-center justify-between gap-2">
              <p className="font-mono text-lg text-chalk-50">
                {evaluation.best_move_san ?? 'No legal move'}
              </p>
              {evaluation.best_move_uci !== null && canPlayBest && (
                <button
                  type="button"
                  onClick={onPlayBest}
                  disabled={busy}
                  className="rounded-lg border border-mint-400/30 bg-mint-400/10 px-3 py-1.5 text-xs font-semibold text-mint-300 transition hover:bg-mint-400/20 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Play it
                </button>
              )}
            </div>
          </div>

          <p className="text-[11px] leading-relaxed text-chalk-500">
            {evaluation.engine.name} {evaluation.engine.version} · depth {evaluation.engine.depth}.
            Mate scores are shown as M1–M30.
          </p>
        </div>
      )}
    </Panel>
  );
}
