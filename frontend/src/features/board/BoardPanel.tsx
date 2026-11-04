import { Chess, type Square } from 'chess.js';
import { useMemo, useState } from 'react';

import { Badge, Eyebrow, Panel } from '../../components/ui';
import { ApiError, type ChesspulseApi } from '../../services/chesspulseApi';
import type { BoardEvaluation, BoardMoveAnalysis } from '../../types/api';
import { ChessBoard, type LastMove } from './ChessBoard';
import { EvaluationCard } from './EvaluationCard';
import { MoveList } from './MoveList';
import { PiecePalette, type EditorTool } from './PiecePalette';
import {
  explainFenError,
  findKing,
  positionFromFen,
  startPosition,
  emptyPosition,
  pieceAt,
  squareToRowCol,
  validatePosition,
  withPiece,
  type Position,
} from './position';

interface BoardPanelProps {
  api: ChesspulseApi;
}

const DEFAULT_TOOL: EditorTool = { color: 'w', type: 'p' };

function moveUci(fen: string, from: Square, to: Square): string | null {
  try {
    const chess = new Chess(fen);
    const candidates = chess
      .moves({ square: from, verbose: true })
      .filter((move) => move.to === to);
    const move = candidates.find((candidate) => candidate.promotion === 'q') ?? candidates[0];
    return move?.lan ?? null;
  } catch {
    return null;
  }
}

function legalTargets(fen: string, square: Square): Square[] {
  try {
    return new Chess(fen).moves({ square, verbose: true }).map((move) => move.to);
  } catch {
    return [];
  }
}

export function BoardPanel({ api }: BoardPanelProps) {
  const [position, setPosition] = useState<Position>(startPosition);
  const [editing, setEditing] = useState(false);
  const [tool, setTool] = useState<EditorTool>(DEFAULT_TOOL);
  const [selected, setSelected] = useState<Square | null>(null);
  const [targets, setTargets] = useState<Square[]>([]);
  const [lastMove, setLastMove] = useState<LastMove | null>(null);
  const [evaluation, setEvaluation] = useState<BoardEvaluation | null>(null);
  const [moves, setMoves] = useState<BoardMoveAnalysis[]>([]);
  const [history, setHistory] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hint, setHint] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const validation = useMemo(() => validatePosition(position), [position]);
  const fen = validation.fen;
  const checkSquare = useMemo(() => {
    if (!validation.ok) return null;
    try {
      const chess = new Chess(fen);
      return chess.inCheck() ? findKing(position, position.turn) : null;
    } catch {
      return null;
    }
  }, [fen, position, validation.ok]);

  function clearReview() {
    setEvaluation(null);
    setMoves([]);
    setHistory([]);
    setLastMove(null);
    setSelected(null);
    setTargets([]);
    setError(null);
    setHint(null);
    setNotice(null);
  }

  function selectSquare(square: Square) {
    setSelected(square);
    setTargets(validation.ok ? legalTargets(fen, square) : []);
  }

  function placePiece(square: Square) {
    if (tool === null) {
      setHint('Choose a piece from the palette first.');
      return;
    }
    const { row, col } = squareToRowCol(square);
    const piece = tool === 'erase' ? null : tool;
    setPosition((current) => ({
      ...current,
      pieces: withPiece(current.pieces, row, col, piece),
      enPassant: null,
    }));
    clearReview();
  }

  function handleSquareClick(square: Square) {
    if (busy) return;
    setError(null);

    if (editing) {
      placePiece(square);
      return;
    }
    if (!validation.ok) {
      setHint(explainFenError(validation.error));
      return;
    }

    if (selected !== null && targets.includes(square)) {
      const uci = moveUci(fen, selected, square);
      if (uci !== null) void analyzeMove(uci, selected, square);
      return;
    }

    const { row, col } = squareToRowCol(square);
    const piece = pieceAt(position.pieces, row, col);
    if (piece !== null && piece.color === position.turn) {
      selectSquare(square);
      return;
    }
    setSelected(null);
    setTargets([]);
  }

  async function analyzeMove(uci: string, from: Square, to: Square) {
    const fenBefore = fen;
    setBusy(true);
    setError(null);
    setHint(null);
    setNotice(null);
    try {
      const result = await api.boardMove(fenBefore, uci);
      setPosition(positionFromFen(result.fen_after));
      setMoves((current) => [...current, result]);
      setHistory((current) => [...current, fenBefore]);
      setEvaluation({
        fen: result.fen_after,
        turn: result.turn === 'white' ? 'black' : 'white',
        status: result.status_after,
        eval_cp: result.eval_after_cp,
        mate: result.mate_after,
        best_move_uci: result.best_move_after_uci,
        best_move_san: result.best_move_after_san,
        engine: result.engine,
      });
      setLastMove({ from, to });
      setSelected(null);
      setTargets([]);
    } catch (cause) {
      setError(
        cause instanceof ApiError ? cause.message : 'The move could not be analysed right now.',
      );
    } finally {
      setBusy(false);
    }
  }

  async function evaluatePosition() {
    if (!validation.ok) {
      setHint(explainFenError(validation.error));
      return;
    }
    setBusy(true);
    setError(null);
    setHint(null);
    setNotice(null);
    try {
      const result = await api.boardEvaluate(fen);
      setEvaluation(result);
      setPosition(positionFromFen(result.fen));
      setLastMove(null);
      setSelected(null);
      setTargets([]);
    } catch (cause) {
      setError(
        cause instanceof ApiError ? cause.message : 'The engine could not evaluate this position.',
      );
    } finally {
      setBusy(false);
    }
  }

  function toggleEditing() {
    if (editing) {
      if (!validation.ok) {
        setHint(explainFenError(validation.error));
        return;
      }
      setEditing(false);
      setHint(null);
      setSelected(null);
      setTargets([]);
      return;
    }
    setEditing(true);
    setSelected(null);
    setTargets([]);
    setHint(null);
    setError(null);
  }

  function changeTurn(turn: 'w' | 'b') {
    if (turn === position.turn) return;
    setPosition((current) => ({ ...current, turn, enPassant: null }));
    clearReview();
  }

  function resetBoard() {
    setPosition(startPosition());
    setEditing(false);
    setTool(DEFAULT_TOOL);
    clearReview();
  }

  function clearBoard() {
    setPosition(emptyPosition());
    setEditing(true);
    setTool(DEFAULT_TOOL);
    clearReview();
  }

  function undo() {
    if (busy || history.length === 0 || moves.length === 0) return;
    const previousFen = history[history.length - 1];
    if (previousFen === undefined) return;
    try {
      setPosition(positionFromFen(previousFen));
    } catch {
      return;
    }
    const remaining = moves.slice(0, -1);
    const last = remaining[remaining.length - 1];
    setHistory((current) => current.slice(0, -1));
    setMoves(remaining);
    setLastMove(null);
    setSelected(null);
    setTargets([]);
    setError(null);
    setEvaluation(
      last === undefined
        ? null
        : {
            fen: previousFen,
            turn: last.turn === 'white' ? 'black' : 'white',
            status: last.status_after,
            eval_cp: last.eval_after_cp,
            mate: last.mate_after,
            best_move_uci: last.best_move_after_uci,
            best_move_san: last.best_move_after_san,
            engine: last.engine,
          },
    );
  }

  function playBest() {
    if (editing || busy || evaluation?.best_move_uci == null) return;
    const uci = evaluation.best_move_uci;
    const from = uci.slice(0, 2) as Square;
    const to = uci.slice(2, 4) as Square;
    void analyzeMove(uci, from, to);
  }

  function copyFen() {
    if (typeof navigator === 'undefined' || navigator.clipboard === undefined) {
      setNotice('Copy is unavailable in this browser.');
      return;
    }
    void navigator.clipboard
      .writeText(fen)
      .then(() => setNotice('FEN copied.'))
      .catch(() => setNotice('Copy failed — select the FEN and copy it manually.'));
  }

  return (
    <section aria-labelledby="board-heading" className="animate-rise space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <Eyebrow>Free board</Eyebrow>
          <h1
            id="board-heading"
            className="mt-1 font-display text-3xl leading-tight tracking-tight text-chalk-50 sm:text-4xl"
          >
            Set up any position. Analyse every move.
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-chalk-400">
            Place pieces freely, then play legal moves. The same Stockfish engine used for game
            reports classifies each move and suggests the best continuation.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={resetBoard}
            className="rounded-xl border border-white/10 bg-board-900/60 px-3 py-2 text-xs font-medium text-chalk-300 transition hover:border-white/20 hover:text-chalk-50"
          >
            Start position
          </button>
          <button
            type="button"
            onClick={clearBoard}
            className="rounded-xl border border-white/10 bg-board-900/60 px-3 py-2 text-xs font-medium text-chalk-300 transition hover:border-coral-400/40 hover:text-coral-300"
          >
            Clear board
          </button>
        </div>
      </div>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)]">
        <div className="space-y-4">
          <Panel className="p-4 sm:p-5">
            <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
              <div>
                <Eyebrow>{editing ? 'Position editor' : 'Play and analyse'}</Eyebrow>
                <p className="mt-1 text-sm text-chalk-300">
                  {editing
                    ? 'Pick a piece and click a square. Use Remove to clear one square.'
                    : 'Click a piece, then a highlighted square to play it.'}
                </p>
              </div>
              <Badge tone={editing ? 'unknown' : 'mint'}>{editing ? 'Editing' : 'Playing'}</Badge>
            </div>

            {editing && <PiecePalette selected={tool} onSelect={setTool} />}

            <div className="mx-auto mt-3 max-w-xl">
              <ChessBoard
                position={position}
                selected={selected}
                targets={targets}
                lastMove={lastMove}
                checkSquare={checkSquare}
                disabled={busy}
                onSquareClick={handleSquareClick}
              />
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={toggleEditing}
                className="rounded-xl bg-mint-400 px-4 py-2 text-sm font-semibold text-on-accent shadow-[0_8px_24px_-10px] shadow-mint-400/80 transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {editing ? 'Play this position' : 'Edit position'}
              </button>

              <div
                role="group"
                aria-label="Side to move"
                className="flex items-center gap-1 rounded-xl border border-white/10 bg-board-900/60 p-1"
              >
                <span className="px-2 text-[10px] uppercase tracking-[0.14em] text-chalk-500">
                  To move
                </span>
                {(['w', 'b'] as const).map((turn) => (
                  <button
                    key={turn}
                    type="button"
                    onClick={() => changeTurn(turn)}
                    aria-pressed={position.turn === turn}
                    className={`rounded-lg px-2.5 py-1.5 text-xs font-medium transition ${
                      position.turn === turn
                        ? 'bg-white/10 text-chalk-50'
                        : 'text-chalk-400 hover:text-chalk-100'
                    }`}
                  >
                    {turn === 'w' ? 'White' : 'Black'}
                  </button>
                ))}
              </div>

              {busy && (
                <span role="status" className="text-xs text-chalk-400">
                  Analysing…
                </span>
              )}
            </div>

            {hint !== null && (
              <p
                role="alert"
                className="mt-3 rounded-xl border border-gold-400/25 bg-gold-400/10 p-3 text-sm text-gold-300"
              >
                {hint}
              </p>
            )}
            {error !== null && (
              <p
                role="alert"
                className="mt-3 rounded-xl border border-coral-400/25 bg-coral-400/10 p-3 text-sm text-coral-300"
              >
                {error}
              </p>
            )}
          </Panel>

          <Panel className="p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <Eyebrow>Position FEN</Eyebrow>
              <button
                type="button"
                onClick={copyFen}
                className="rounded-lg border border-white/10 px-2.5 py-1 text-[11px] font-medium text-chalk-400 transition hover:border-white/20 hover:text-chalk-100"
              >
                Copy FEN
              </button>
            </div>
            <input
              readOnly
              value={fen}
              aria-label="Position FEN"
              aria-invalid={!validation.ok}
              onFocus={(event) => event.currentTarget.select()}
              className="mt-2 w-full rounded-lg border border-white/10 bg-board-950/60 px-3 py-2 font-mono text-xs text-chalk-200 outline-none focus:border-mint-400/50"
            />
            {!validation.ok && (
              <p className="mt-2 text-xs text-gold-300">{explainFenError(validation.error)}</p>
            )}
            {notice !== null && <p className="mt-2 text-xs text-chalk-400">{notice}</p>}
          </Panel>
        </div>

        <div className="space-y-4">
          <EvaluationCard
            evaluation={evaluation}
            busy={busy}
            canPlayBest={!editing && validation.ok}
            onEvaluate={() => void evaluatePosition()}
            onPlayBest={playBest}
          />
          <MoveList moves={moves} busy={busy} onUndo={undo} />
        </div>
      </div>
    </section>
  );
}
