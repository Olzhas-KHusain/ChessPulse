import { Chess, type Square } from 'chess.js';
import { useCallback, useMemo, useState } from 'react';

import { ChessBoard, type LastMove } from '../board/ChessBoard';
import type { Position } from '../board/position';
import { Panel } from '../../components/ui';
import type { AnalysedMove } from '../../types/api';

/**
 * Replays one game on a board and lets the user try alternative moves (branches).
 *
 * The main line comes from the game's PGN (SAN moves). From any position the user
 * can play a trial move by clicking a piece and then a target square; trial moves
 * form a branch that can be discarded with "Back to main line". Navigation moves
 * along the main line only.
 */
export interface GameBoardProps {
  /** SAN moves of the main line, in order. */
  sanMoves: string[];
  /** Optional engine analysis of the main line, matched by UCI. */
  analysedMoves?: AnalysedMove[];
}

export function GameBoard({ sanMoves, analysedMoves }: GameBoardProps) {
  const analysisByUci = useMemo(
    () => new Map((analysedMoves ?? []).map((move) => [move.uci, move])),
    [analysedMoves],
  );

  const [mainPly, setMainPly] = useState(0);
  const [branchSans, setBranchSans] = useState<string[]>([]);
  const [selected, setSelected] = useState<Square | null>(null);

  const currentSans = useMemo(
    () => [...sanMoves.slice(0, mainPly), ...branchSans],
    [sanMoves, mainPly, branchSans],
  );

  const position = useMemo(() => {
    const chess = new Chess();
    for (const san of currentSans) {
      if (chess.move(san) === null) break;
    }
    return chess;
  }, [currentSans]);

  const fen = position.fen();
  const isGameOver = position.isGameOver();
  const canBack = mainPly > 0 || branchSans.length > 0;
  const canForward = mainPly < sanMoves.length;

  const legalTargets = useCallback(
    (square: Square): Square[] => {
      try {
        return position.moves({ square, verbose: true }).map((move) => move.to);
      } catch {
        return [];
      }
    },
    [position],
  );

  const analysisFor = useCallback(
    (uci: string): AnalysedMove | undefined => analysisByUci.get(uci),
    [analysisByUci],
  );

  /** UCI of the move at the given 0-based ply in currentSans. */
  const uciAtPly = useCallback(
    (ply: number): string | null => {
      try {
        const chess = new Chess();
        for (let i = 0; i < ply; i += 1) {
          if (chess.move(currentSans[i]!) === null) return null;
        }
        const move = chess.move(currentSans[ply]!);
        return move?.lan ?? null;
      } catch {
        return null;
      }
    },
    [currentSans],
  );

  function jumpToPly(ply: number) {
    setMainPly(ply);
    setBranchSans([]);
    setSelected(null);
  }

  function playTrialMove(san: string) {
    const chess = new Chess(fen);
    if (chess.move(san) === null) return;
    setBranchSans((current) => [...current, san]);
    setSelected(null);
  }

  function handleSquareClick(square: Square) {
    if (isGameOver) return;
    if (selected !== null) {
      const candidates = position.moves({ square: selected, verbose: true });
      const move = candidates.find((candidate) => candidate.to === square);
      if (move !== undefined) {
        playTrialMove(move.san);
      }
      setSelected(null);
      return;
    }
    const piece = position.get(square) as { color: string; type: string } | null;
    if (piece !== null) {
      setSelected(square);
    }
  }

  function back() {
    setSelected(null);
    if (branchSans.length > 0) {
      setBranchSans((current) => current.slice(0, -1));
    } else if (mainPly > 0) {
      setMainPly((current) => current - 1);
    }
  }

  function forward() {
    setSelected(null);
    if (mainPly < sanMoves.length) {
      setMainPly((current) => current + 1);
      setBranchSans([]);
    }
  }

  function backToMainLine() {
    setSelected(null);
    setBranchSans([]);
  }

  const moveNumberFromPly = (ply: number) => Math.floor(ply / 2) + 1;

  return (
    <Panel className="overflow-hidden">
      <div className="grid gap-4 lg:grid-cols-[1fr_320px] p-4 sm:p-5">
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-medium text-chalk-100">Board</h3>
            <div className="flex gap-1">
              <button
                type="button"
                onClick={back}
                disabled={!canBack}
                className="rounded-lg border border-white/10 bg-board-900/60 px-2.5 py-1 text-[10px] font-medium text-chalk-300 transition disabled:opacity-40 disabled:cursor-not-allowed hover:border-white/20 hover:text-chalk-50"
              >
                ◀ Back
              </button>
              <button
                type="button"
                onClick={forward}
                disabled={!canForward}
                className="rounded-lg border border-white/10 bg-board-900/60 px-2.5 py-1 text-[10px] font-medium text-chalk-300 transition disabled:opacity-40 disabled:cursor-not-allowed hover:border-white/20 hover:text-chalk-50"
              >
                Forward ▶
              </button>
              {branchSans.length > 0 && (
                <button
                  type="button"
                  onClick={backToMainLine}
                  className="ml-1 rounded-lg border border-white/10 bg-board-900/60 px-2.5 py-1 text-[10px] font-medium text-chalk-300 transition hover:border-coral-400/40 hover:text-coral-300"
                >
                  Main line
                </button>
              )}
            </div>
          </div>

          <div className="mx-auto mt-2 max-w-[380px]">
            <ChessBoard
              position={boardPosition(position)}
              selected={selected}
              targets={selected !== null ? legalTargets(selected) : []}
              lastMove={
                currentSans.length > 0
                  ? lastMoveFromSans(currentSans[currentSans.length - 1]!)
                  : null
              }
              disabled={isGameOver}
              onSquareClick={handleSquareClick}
            />
          </div>

          <p className="mt-1 text-xs text-chalk-500 text-center">
            {isGameOver
              ? position.isCheckmate()
                ? 'Checkmate'
                : position.isStalemate()
                  ? 'Stalemate'
                  : 'Game over'
              : `${position.turn() === 'w' ? 'White' : 'Black'} to move`}
          </p>

          {branchSans.length > 0 && (
            <div className="mt-2 rounded-xl border border-coral-400/25 bg-coral-400/10 p-3 text-sm">
              <p className="text-xs uppercase tracking-[0.14em] text-coral-400 mb-1">
                Trial branch
              </p>
              <div className="font-mono text-xs text-chalk-100 overflow-x-auto whitespace-nowrap">
                {branchSans.map((san, i) => (
                  <span key={i} className="inline-block mr-2">
                    {moveNumberFromPly(mainPly + i)}. {san}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="space-y-4">
          <h3 className="text-sm font-medium text-chalk-100">Moves</h3>
          {sanMoves.length === 0 ? (
            <p className="mt-3 rounded-xl border border-dashed border-white/15 bg-board-900/40 p-3 text-sm text-chalk-400">
              No moves to show.
            </p>
          ) : (
            <div className="overflow-y-auto max-h-[420px] border border-white/[0.06] rounded-xl p-2">
              <ol className="divide-y divide-white/[0.05] font-mono text-sm">
                {sanMoves.map((san, i) => {
                  const ply = i;
                  const isCurrent = ply < mainPly;
                  const isBranch = ply >= mainPly && ply - mainPly < branchSans.length;
                  const moveNum = moveNumberFromPly(ply);
                  const uci = uciAtPly(ply);
                  const analysis = uci === null ? undefined : analysisFor(uci);
                  return (
                    <li
                      key={i}
                      className="flex items-center justify-between gap-2 px-2 py-1.5 rounded transition-colors cursor-pointer hover:bg-white/[0.04]"
                      onClick={() => jumpToPly(i + 1)}
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="w-12 shrink-0 tabular-nums text-chalk-500">
                          {moveNum}.{ply % 2 === 1 ? '…' : ''}
                        </span>
                        <span
                          className={`tabular-nums ${
                            isCurrent
                              ? 'text-mint-300'
                              : isBranch
                                ? 'text-coral-300'
                                : 'text-chalk-100'
                          } font-mono`}
                        >
                          {san}
                        </span>
                        {analysis !== undefined && (
                          <span className="flex items-center gap-1 text-xs">
                            {analysis.classification === 'best' ? (
                              <span className="text-mint-300" title="Best move">
                                ★
                              </span>
                            ) : (
                              <span
                                className={
                                  analysis.classification === 'blunder'
                                    ? 'text-coral-300'
                                    : analysis.classification === 'mistake'
                                      ? 'text-gold-300'
                                      : 'text-chalk-500'
                                }
                                title={analysis.classification}
                              >
                                −{analysis.cp_loss} cp
                              </span>
                            )}
                          </span>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ol>
            </div>
          )}
        </div>
      </div>
    </Panel>
  );
}

/** Convert a chess.js instance to the local Position model used by ChessBoard. */
function boardPosition(chess: Chess): Position {
  const board = chess.board();
  return {
    pieces: board.map((row) => row.map((piece) => piece ?? null)),
    turn: chess.turn() as 'w' | 'b',
    enPassant: null,
  };
}

/** Play one SAN move from the start and return its long-algebraic (UCI-like) notation. */
function lastMoveFromSans(san: string): LastMove | null {
  try {
    const chess = new Chess();
    const move = chess.move(san);
    if (move === null) return null;
    return { from: move.from as Square, to: move.to as Square };
  } catch {
    return null;
  }
}
