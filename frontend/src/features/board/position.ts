/**
 * Board position model for the free analysis board.
 *
 * The editor stores an 8x8 grid rather than a `Chess` instance because users may
 * build positions that are not legal yet (for example, before placing both
 * kings). A FEN is derived from the grid and validated only when the user wants
 * to play or evaluate it.
 */
import { validateFen, type PieceSymbol, type Square } from 'chess.js';

export type PieceColor = 'w' | 'b';
export type PieceType = PieceSymbol;
export type BoardPieces = (Piece | null)[][];

export interface Piece {
  color: PieceColor;
  type: PieceType;
}

export interface Position {
  pieces: BoardPieces;
  turn: PieceColor;
  /** En passant target square, preserved from a server position. */
  enPassant: Square | null;
}

export const START_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
export const FILES = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'] as const;
export const RANKS = ['8', '7', '6', '5', '4', '3', '2', '1'] as const;

export const PIECE_GLYPHS: Record<PieceType, string> = {
  k: '♚',
  q: '♛',
  r: '♜',
  b: '♝',
  n: '♞',
  p: '♟',
};

export const PIECE_NAMES: Record<PieceType, string> = {
  k: 'king',
  q: 'queen',
  r: 'rook',
  b: 'bishop',
  n: 'knight',
  p: 'pawn',
};

export function emptyPieces(): BoardPieces {
  return Array.from({ length: 8 }, () => Array.from({ length: 8 }, () => null));
}

export function emptyPosition(): Position {
  return { pieces: emptyPieces(), turn: 'w', enPassant: null };
}

export function startPosition(): Position {
  return positionFromFen(START_FEN);
}

export function pieceAt(pieces: BoardPieces, row: number, col: number): Piece | null {
  return pieces[row]?.[col] ?? null;
}

export function withPiece(
  pieces: BoardPieces,
  row: number,
  col: number,
  piece: Piece | null,
): BoardPieces {
  return pieces.map((line, rowIndex) =>
    line.map((current, colIndex) => (rowIndex === row && colIndex === col ? piece : current)),
  );
}

export function squareName(row: number, col: number): Square {
  const file = FILES[col];
  const rank = RANKS[row];
  if (file === undefined || rank === undefined) throw new Error('Square out of range');
  return `${file}${rank}`;
}

export function squareToRowCol(square: Square): { row: number; col: number } {
  const col = FILES.indexOf(square[0] as (typeof FILES)[number]);
  const row = RANKS.indexOf(square[1] as (typeof RANKS)[number]);
  return { row, col };
}

export function isLightSquare(row: number, col: number): boolean {
  return (row + col) % 2 === 0;
}

export function findKing(position: Position, color: PieceColor): Square | null {
  for (let row = 0; row < 8; row += 1) {
    for (let col = 0; col < 8; col += 1) {
      const piece = pieceAt(position.pieces, row, col);
      if (piece !== null && piece.color === color && piece.type === 'k') {
        return squareName(row, col);
      }
    }
  }
  return null;
}

function pieceChar(piece: Piece): string {
  return piece.color === 'w' ? piece.type.toUpperCase() : piece.type;
}

function pieceOn(pieces: BoardPieces, square: Square): Piece | null {
  const { row, col } = squareToRowCol(square);
  return pieceAt(pieces, row, col);
}

function isPiece(piece: Piece | null, color: PieceColor, type: PieceType): boolean {
  return piece !== null && piece.color === color && piece.type === type;
}

/** Standard castling rights that are still consistent with the current setup. */
function castlingRights(pieces: BoardPieces): string {
  let rights = '';
  if (isPiece(pieceOn(pieces, 'e1'), 'w', 'k')) {
    if (isPiece(pieceOn(pieces, 'h1'), 'w', 'r')) rights += 'K';
    if (isPiece(pieceOn(pieces, 'a1'), 'w', 'r')) rights += 'Q';
  }
  if (isPiece(pieceOn(pieces, 'e8'), 'b', 'k')) {
    if (isPiece(pieceOn(pieces, 'h8'), 'b', 'r')) rights += 'k';
    if (isPiece(pieceOn(pieces, 'a8'), 'b', 'r')) rights += 'q';
  }
  return rights || '-';
}

export function fenFromPosition(position: Position): string {
  const rows = position.pieces.map((line) => {
    let out = '';
    let empty = 0;
    for (const piece of line) {
      if (piece === null) {
        empty += 1;
        continue;
      }
      if (empty > 0) {
        out += String(empty);
        empty = 0;
      }
      out += pieceChar(piece);
    }
    if (empty > 0) out += String(empty);
    return out;
  });
  return `${rows.join('/')} ${position.turn} ${castlingRights(position.pieces)} ${
    position.enPassant ?? '-'
  } 0 1`;
}

export function positionFromFen(fen: string): Position {
  const parts = fen.trim().split(/\s+/);
  const boardPart = parts[0] ?? '';
  const turnPart = parts[1] ?? 'w';
  const enPassantPart = parts[3] ?? '-';
  const rows = boardPart.split('/');
  if (rows.length !== 8) throw new Error('A FEN must contain eight ranks.');

  const pieces = emptyPieces();
  rows.forEach((rank, rowIndex) => {
    let col = 0;
    for (const char of rank) {
      if (/^[1-8]$/.test(char)) {
        col += Number(char);
        continue;
      }
      const type = char.toLowerCase();
      if (!/^[pnbrqk]$/.test(type) || col > 7) {
        throw new Error('Unsupported piece placement in FEN.');
      }
      const line = pieces[rowIndex];
      if (line === undefined) throw new Error('Unsupported piece placement in FEN.');
      line[col] = { color: char === type ? 'b' : 'w', type: type as PieceType };
      col += 1;
    }
    if (col !== 8) throw new Error('Every FEN rank must describe eight squares.');
  });

  return {
    pieces,
    turn: turnPart === 'b' ? 'b' : 'w',
    enPassant: /^[a-h][36]$/.test(enPassantPart) ? (enPassantPart as Square) : null,
  };
}

export interface FenValidation {
  fen: string;
  ok: boolean;
  error: string | null;
}

export function validatePosition(position: Position): FenValidation {
  const fen = fenFromPosition(position);
  const result = validateFen(fen);
  return { fen, ok: result.ok, error: result.error ?? null };
}

/** A short, human-readable reason for the most common editing mistakes. */
export function explainFenError(error: string | null): string {
  if (error === null) return 'This position cannot be played.';
  if (/king/i.test(error)) return 'Each side needs exactly one king.';
  if (/pawn/i.test(error)) return 'Pawns cannot stand on the first or last rank.';
  return error;
}
