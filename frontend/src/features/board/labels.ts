import type { BadgeTone } from '../../components/ui';
import type { BoardStatus, MoveClassification } from '../../types/api';

export const BOARD_STATUS_LABEL: Record<BoardStatus, string> = {
  ongoing: 'Play continues',
  checkmate: 'Checkmate',
  stalemate: 'Stalemate',
  insufficient_material: 'Draw — insufficient material',
  seventyfive_moves: 'Draw — seventy-five-move rule',
  fivefold_repetition: 'Draw — fivefold repetition',
};

export const CLASSIFICATION_LABEL: Record<MoveClassification, string> = {
  best: 'Best',
  good: 'Good',
  inaccuracy: 'Inaccuracy',
  mistake: 'Mistake',
  blunder: 'Blunder',
};

export const CLASSIFICATION_TONE: Record<MoveClassification, BadgeTone> = {
  best: 'win',
  good: 'neutral',
  inaccuracy: 'unknown',
  mistake: 'draw',
  blunder: 'loss',
};
