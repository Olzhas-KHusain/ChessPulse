import type { Square } from 'chess.js';
import type { CSSProperties } from 'react';

import {
  FILES,
  PIECE_GLYPHS,
  PIECE_NAMES,
  RANKS,
  isLightSquare,
  squareName,
  type Position,
} from './position';

export interface LastMove {
  from: Square;
  to: Square;
}

interface ChessBoardProps {
  position: Position;
  selected: Square | null;
  targets: Square[];
  lastMove: LastMove | null;
  checkSquare?: Square | null;
  disabled?: boolean;
  onSquareClick: (square: Square) => void;
}

const WHITE_PIECE = '#fffdf7';
const BLACK_PIECE = '#18222d';

function pieceStyle(color: 'w' | 'b'): CSSProperties {
  return color === 'w'
    ? {
        color: WHITE_PIECE,
        WebkitTextStroke: '1px #1b2732',
        textShadow: '0 1px 2px rgb(0 0 0 / 0.45)',
      }
    : { color: BLACK_PIECE, textShadow: '0 1px 1px rgb(255 255 255 / 0.25)' };
}

/**
 * Interactive 8x8 board. Every square is a real button, so the board is usable
 * with a keyboard and screen readers; the glyph is decorative.
 */
export function ChessBoard({
  position,
  selected,
  targets,
  lastMove,
  checkSquare = null,
  disabled = false,
  onSquareClick,
}: ChessBoardProps) {
  const targetSet = new Set(targets);

  return (
    <div
      role="group"
      aria-label="Chess board"
      className="grid grid-cols-8 overflow-hidden rounded-xl border border-white/15 shadow-lift"
    >
      {position.pieces.map((line, row) =>
        line.map((piece, col) => {
          const square = squareName(row, col);
          const light = isLightSquare(row, col);
          const isSelected = selected === square;
          const isTarget = targetSet.has(square);
          const isLast = lastMove !== null && (lastMove.from === square || lastMove.to === square);
          const isCheck = checkSquare === square;
          const pieceName = piece === null ? '' : ` ${PIECE_NAMES[piece.type]}`;
          const colorName = piece === null ? '' : piece.color === 'w' ? ' white' : ' black';
          const coordinateClass = light ? 'text-[#59645b]' : 'text-[#f2eee4]';

          return (
            <button
              key={square}
              type="button"
              onClick={() => onSquareClick(square)}
              disabled={disabled}
              aria-label={`${square}${colorName}${pieceName}`}
              aria-pressed={isSelected}
              className={`relative aspect-square select-none transition-colors disabled:cursor-wait ${
                light ? 'bg-square-light' : 'bg-square-dark'
              }`}
            >
              {isLast && <span aria-hidden="true" className="absolute inset-0 bg-square-last" />}
              {isCheck && (
                <span aria-hidden="true" className="absolute inset-0 bg-square-check/70" />
              )}
              {isSelected && (
                <span
                  aria-hidden="true"
                  className="absolute inset-0 ring-4 ring-inset ring-square-selected"
                />
              )}
              {isTarget &&
                (piece === null ? (
                  <span
                    aria-hidden="true"
                    className="absolute left-1/2 top-1/2 h-1/4 w-1/4 -translate-x-1/2 -translate-y-1/2 rounded-full bg-square-selected/85"
                  />
                ) : (
                  <span
                    aria-hidden="true"
                    className="absolute inset-0 ring-4 ring-inset ring-square-selected/85"
                  />
                ))}

              {piece !== null && (
                <span
                  aria-hidden="true"
                  className="relative z-10 block text-[clamp(1.35rem,5.4vw,2.8rem)] leading-none"
                  style={pieceStyle(piece.color)}
                >
                  {PIECE_GLYPHS[piece.type]}
                </span>
              )}

              {col === 0 && (
                <span
                  aria-hidden="true"
                  className={`absolute left-0.5 top-0.5 text-[9px] font-semibold leading-none ${coordinateClass}`}
                >
                  {RANKS[row]}
                </span>
              )}
              {row === 7 && (
                <span
                  aria-hidden="true"
                  className={`absolute bottom-0.5 right-0.5 text-[9px] font-semibold leading-none ${coordinateClass}`}
                >
                  {FILES[col]}
                </span>
              )}
            </button>
          );
        }),
      )}
    </div>
  );
}
