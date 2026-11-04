import { describe, expect, it } from 'vitest';

import {
  START_FEN,
  emptyPosition,
  fenFromPosition,
  findKing,
  pieceAt,
  positionFromFen,
  squareToRowCol,
  startPosition,
  validatePosition,
  withPiece,
} from './position';

describe('position model', () => {
  it('round-trips the standard start position', () => {
    const position = startPosition();
    expect(fenFromPosition(position)).toBe(START_FEN);
    expect(position.turn).toBe('w');
    expect(pieceAt(position.pieces, 7, 4)?.type).toBe('k');
  });

  it('reads the side to move from a FEN', () => {
    const position = positionFromFen('rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1');
    expect(position.turn).toBe('b');
    expect(pieceAt(position.pieces, 4, 4)?.type).toBe('p');
  });

  it('preserves an en passant target square', () => {
    const position = positionFromFen(
      'rnbqkbnr/ppp1pppp/8/3pP3/8/8/PPPP1PPP/RNBQKBNR w KQkq d6 0 3',
    );
    expect(position.enPassant).toBe('d6');
    expect(fenFromPosition(position)).toContain(' w KQkq d6 ');
  });

  it('places and removes pieces immutably', () => {
    const position = emptyPosition();
    const withKing = withPiece(position.pieces, 7, 4, { color: 'w', type: 'k' });
    expect(pieceAt(position.pieces, 7, 4)).toBeNull();
    expect(pieceAt(withKing, 7, 4)).toEqual({ color: 'w', type: 'k' });

    const removed = withPiece(withKing, 7, 4, null);
    expect(pieceAt(removed, 7, 4)).toBeNull();
  });

  it('derives castling rights from king and rook placement', () => {
    const position = startPosition();
    const noH1Rook = withPiece(position.pieces, 7, 7, null);
    expect(fenFromPosition({ ...position, pieces: noH1Rook })).toContain(' w Qkq ');
  });

  it('rejects an empty board until both kings exist', () => {
    const empty = validatePosition(emptyPosition());
    expect(empty.ok).toBe(false);

    const kings = withPiece(
      withPiece(emptyPosition().pieces, 7, 4, { color: 'w', type: 'k' }),
      0,
      4,
      { color: 'b', type: 'k' },
    );
    expect(validatePosition({ pieces: kings, turn: 'w', enPassant: null }).ok).toBe(true);
  });

  it('finds each king and converts squares', () => {
    const position = startPosition();
    expect(findKing(position, 'w')).toBe('e1');
    expect(findKing(position, 'b')).toBe('e8');
    expect(squareToRowCol('a8')).toEqual({ row: 0, col: 0 });
    expect(squareToRowCol('h1')).toEqual({ row: 7, col: 7 });
  });
});
