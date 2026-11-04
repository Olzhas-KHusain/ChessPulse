import type { CSSProperties } from 'react';

import { PIECE_GLYPHS, PIECE_NAMES, type Piece, type PieceColor, type PieceType } from './position';

const PIECE_ORDER: PieceType[] = ['k', 'q', 'r', 'b', 'n', 'p'];

export type EditorTool = Piece | 'erase' | null;

interface PiecePaletteProps {
  selected: EditorTool;
  onSelect: (tool: EditorTool) => void;
}

const WHITE_PIECE = '#fffdf7';
const BLACK_PIECE = '#18222d';

function swatchStyle(color: PieceColor): CSSProperties {
  return color === 'w'
    ? { color: WHITE_PIECE, WebkitTextStroke: '1px #1b2732' }
    : { color: BLACK_PIECE };
}

function sameTool(a: EditorTool, b: EditorTool): boolean {
  if (a === null || b === null) return a === b;
  if (a === 'erase' || b === 'erase') return a === b;
  return a.color === b.color && a.type === b.type;
}

export function PiecePalette({ selected, onSelect }: PiecePaletteProps) {
  return (
    <div className="space-y-2">
      <p className="text-xs text-chalk-400">
        Pick a piece, then click a square to place it. Click again to replace.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        {(['w', 'b'] as const).map((color) => (
          <div
            key={color}
            role="group"
            aria-label={`${color === 'w' ? 'White' : 'Black'} pieces`}
            className="flex items-center gap-1 rounded-xl border border-white/10 bg-board-900/60 p-1"
          >
            {PIECE_ORDER.map((type) => {
              const piece: Piece = { color, type };
              const active = sameTool(selected, piece);
              return (
                <button
                  key={type}
                  type="button"
                  onClick={() => onSelect(piece)}
                  aria-pressed={active}
                  aria-label={`${color === 'w' ? 'White' : 'Black'} ${PIECE_NAMES[type]}`}
                  title={`${color === 'w' ? 'White' : 'Black'} ${PIECE_NAMES[type]}`}
                  className={`grid h-9 w-9 place-items-center rounded-lg text-2xl leading-none transition ${
                    active ? 'bg-mint-400/25 ring-2 ring-inset ring-mint-400' : 'hover:bg-white/10'
                  }`}
                >
                  <span aria-hidden="true" style={swatchStyle(color)}>
                    {PIECE_GLYPHS[type]}
                  </span>
                </button>
              );
            })}
          </div>
        ))}
        <button
          type="button"
          onClick={() => onSelect('erase')}
          aria-pressed={selected === 'erase'}
          className={`inline-flex h-11 items-center gap-2 rounded-xl border px-3 text-xs font-medium transition ${
            selected === 'erase'
              ? 'border-coral-400/50 bg-coral-400/15 text-coral-300'
              : 'border-white/10 bg-board-900/60 text-chalk-300 hover:bg-white/10'
          }`}
        >
          <span aria-hidden="true">⌫</span>
          Remove
        </button>
      </div>
    </div>
  );
}
