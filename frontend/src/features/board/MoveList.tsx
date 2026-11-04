import { Badge, Eyebrow, Panel } from '../../components/ui';
import type { BoardMoveAnalysis } from '../../types/api';
import { formatEvaluation } from './evaluation';
import { CLASSIFICATION_LABEL, CLASSIFICATION_TONE } from './labels';

interface MoveListProps {
  moves: BoardMoveAnalysis[];
  busy: boolean;
  onUndo: () => void;
}

export function MoveList({ moves, busy, onUndo }: MoveListProps) {
  return (
    <Panel className="p-4 sm:p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <Eyebrow>Move review</Eyebrow>
          <h2 className="mt-1 font-display text-2xl tracking-tight text-chalk-50">Played moves</h2>
        </div>
        <button
          type="button"
          onClick={onUndo}
          disabled={busy || moves.length === 0}
          className="rounded-lg border border-white/10 bg-board-900/60 px-3 py-1.5 text-xs font-medium text-chalk-300 transition hover:border-white/20 hover:text-chalk-50 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Undo
        </button>
      </div>

      {moves.length === 0 ? (
        <p className="mt-4 rounded-xl border border-dashed border-white/15 bg-board-900/40 p-3 text-sm leading-relaxed text-chalk-400">
          No moves yet. Play a move on the board and the engine will classify it.
        </p>
      ) : (
        <ol className="mt-3 divide-y divide-white/[0.06]">
          {moves.map((move, index) => (
            <li
              key={`${index}-${move.uci}`}
              className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm"
            >
              <span className="flex min-w-0 items-center gap-2">
                <span className="w-8 shrink-0 tabular-nums text-chalk-500">
                  {move.move_number}
                  {move.turn === 'white' ? '.' : '…'}
                </span>
                <span className="font-mono text-chalk-100">{move.san}</span>
                <Badge tone={CLASSIFICATION_TONE[move.classification]}>
                  {CLASSIFICATION_LABEL[move.classification]}
                </Badge>
              </span>
              <span className="flex items-center gap-3 text-xs text-chalk-500">
                <span title="Centipawn loss from the mover's perspective">
                  {move.cp_loss === 0 ? '0 cp' : `−${move.cp_loss} cp`}
                </span>
                <span className="font-mono tabular-nums text-chalk-300">
                  {formatEvaluation(move.eval_after_cp, move.mate_after)}
                </span>
              </span>
            </li>
          ))}
        </ol>
      )}
    </Panel>
  );
}
