/** Synthetic API responses for component tests (shapes match docs/specs/api-*.md). */
import type {
  AnalysisState,
  AnalyzeScope,
  FormReport,
  GameDetail,
  GameList,
  GameSummary,
  Openings,
  Opponents,
  Overview,
  RatingHistory,
} from '../types/api';

const period = {
  start: '2026-09-20T12:00:00Z',
  end: '2026-10-20T12:00:00Z',
  timezone: 'UTC' as const,
};
const meta = {
  data_status: 'fresh' as const,
  refresh_error: null,
  as_of: '2026-10-20T12:00:00Z',
  last_successful_update: '2026-10-20T12:00:00Z',
};

export const overview: Overview = {
  username: 'example_player',
  period,
  games_count: 42,
  wins: 22,
  losses: 16,
  draws: 4,
  unknown_results: 0,
  win_rate: 52.38,
  current_rating: 1523,
  current_rating_detail: { rating: 1523, as_of: '2026-10-19T10:00:00Z', source: 'provider_stats' },
  current_streak: { type: 'win', length: 3 },
  longest_winning_streak: 5,
  streak_may_be_incomplete: false,
  missing_sections: [],
  ...meta,
};

export const emptyOverview: Overview = {
  ...overview,
  games_count: 0,
  wins: 0,
  losses: 0,
  draws: 0,
  win_rate: null,
  current_rating: null,
  current_rating_detail: null,
  current_streak: null,
  longest_winning_streak: null,
  missing_sections: ['current_rating'],
};

export const ratingHistory: RatingHistory = {
  username: 'example_player',
  period,
  points: [
    { timestamp: '2026-10-01T10:00:00Z', rating: 1500, source: 'game_record', game_id: 1 },
    { timestamp: '2026-10-02T10:00:00Z', rating: 1512, source: 'game_record', game_id: 2 },
  ],
  rating_semantics: 'reported_with_game',
  coverage: 'complete',
  games_considered: 2,
  games_without_rating: 0,
  duplicates_removed: 0,
  ...meta,
};

export const emptyRatingHistory: RatingHistory = {
  ...ratingHistory,
  points: [],
  coverage: 'none',
  games_considered: 0,
};

export const openings: Openings = {
  username: 'example_player',
  period,
  sort: 'games',
  total_groups: 2,
  items: [
    {
      opening_key: 'Sicilian-Defense',
      name: 'Sicilian Defense',
      eco_code: 'B20',
      is_unknown: false,
      games_count: 3,
      wins: 2,
      losses: 1,
      draws: 0,
      unknown_results: 0,
      win_rate: 66.67,
    },
    {
      opening_key: null,
      name: 'Unknown',
      eco_code: null,
      is_unknown: true,
      games_count: 1,
      wins: 0,
      losses: 0,
      draws: 0,
      unknown_results: 1,
      win_rate: null,
    },
  ],
  ...meta,
};

export const opponents: Opponents = {
  username: 'example_player',
  period,
  perspective: 'searched_player',
  sort: 'games',
  total_groups: 1,
  items: [
    {
      opponent_username: 'rival_one',
      profile_url: 'https://www.chess.com/member/rival_one',
      last_played_at: '2026-10-10T10:00:00Z',
      last_rating: null,
      games_count: 2,
      wins: 1,
      losses: 1,
      draws: 0,
      unknown_results: 0,
      win_rate: 50,
    },
  ],
  ...meta,
};

export function gameSummary(id: number, opponent = `rival_${id}`): GameSummary {
  return {
    game_id: `live:${id}`,
    played_at: `2026-10-${String(10 + (id % 10)).padStart(2, '0')}T10:00:00Z`,
    result: 'win',
    color: 'white',
    player_rating: 1500,
    opponent: { username: opponent, rating: null },
    time_control: '600',
    rated: true,
    opening: null,
    game_url: `https://www.chess.com/game/live/${id}`,
  };
}

export const missingAnalysis: AnalysisState = {
  username: 'example_player',
  game_id: 'live:1',
  status: 'missing',
  error_code: null,
  requested_at: null,
  completed_at: null,
  analysis: null,
};

export function completedAnalysis(): AnalysisState {
  return {
    ...missingAnalysis,
    status: 'completed',
    completed_at: '2026-10-20T12:05:00Z',
    analysis: {
      schema_version: 1,
      engine: { name: 'Stockfish', version: '19', depth: 12 },
      players: { white: 'example_player', black: 'rival_1' },
      result: '1-0',
      moves: [
        {
          ply: 1,
          move_number: 1,
          color: 'white',
          san: 'e4',
          uci: 'e2e4',
          eval_before_cp: 20,
          eval_cp: 25,
          mate: null,
          best_move_uci: 'e2e4',
          best_move_san: 'e4',
          cp_loss: 0,
          classification: 'best',
        },
        {
          ply: 2,
          move_number: 1,
          color: 'black',
          san: 'e5',
          uci: 'e7e5',
          eval_before_cp: 25,
          eval_cp: 30,
          mate: null,
          best_move_uci: 'e7e5',
          best_move_san: 'e5',
          cp_loss: 0,
          classification: 'best',
        },
        {
          ply: 3,
          move_number: 2,
          color: 'white',
          san: 'Nf3',
          uci: 'g1f3',
          eval_before_cp: 30,
          eval_cp: 180,
          mate: null,
          best_move_uci: 'f1c4',
          best_move_san: 'Bc4',
          cp_loss: 150,
          classification: 'mistake',
        },
      ],
      summary: {
        white: {
          accuracy: 84,
          acpl: 50,
          moves: 2,
          counts: { best: 1, good: 0, inaccuracy: 0, mistake: 1, blunder: 0 },
        },
        black: {
          accuracy: 90,
          acpl: 20,
          moves: 1,
          counts: { best: 1, good: 0, inaccuracy: 0, mistake: 0, blunder: 0 },
        },
      },
    },
  };
}

export function gameList(ids: number[], nextCursor: string | null): GameList {
  return {
    username: 'example_player',
    period,
    result_filter: null,
    items: ids.map((id) => gameSummary(id)),
    next_cursor: nextCursor,
    ...meta,
  };
}

export function gameDetail(
  id: number,
  pgnStatus: 'available' | 'missing' | 'malformed',
): GameDetail {
  return {
    username: 'example_player',
    game: gameSummary(id),
    rating_semantics: 'reported_with_game',
    pgn: {
      status: pgnStatus,
      headers: {},
      moves_san: pgnStatus === 'available' ? ['e4', 'e5', 'Nf3'] : null,
      error: pgnStatus === 'malformed' ? 'illegal_move' : null,
      raw: null,
    },
    ...meta,
  };
}

export const formReport: FormReport = {
  username: 'example_player',
  period,
  time_class: 'rapid',
  games_total: 5,
  games_analyzed: 4,
  games_queued: 1,
  games_running: 0,
  games_failed: 0,
  accuracy_mean: 82.4,
  opponent_accuracy_mean: 78.1,
  acpl_mean: 64.2,
  wp_loss_per_game: 18.6,
  accuracy_trend: [
    {
      game_id: 'live:1',
      played_at: '2026-10-10T10:00:00Z',
      color: 'white',
      result: 'win',
      opponent: 'rival_1',
      accuracy: 86.1,
      acpl: 48.2,
      blunders: 0,
      mistakes: 1,
    },
    {
      game_id: 'live:2',
      played_at: '2026-10-11T10:00:00Z',
      color: 'black',
      result: 'loss',
      opponent: 'rival_2',
      accuracy: 74.3,
      acpl: 91.4,
      blunders: 2,
      mistakes: 3,
    },
  ],
  by_phase: [
    {
      key: 'opening',
      label: 'Opening (moves 1–10)',
      games: 4,
      moves: 40,
      blunders: 1,
      mistakes: 2,
      inaccuracies: 3,
      acpl: 32.1,
      accuracy: 88.2,
      wp_loss_per_game: 4.1,
    },
    {
      key: 'middlegame',
      label: 'Middlegame (moves 11–30)',
      games: 4,
      moves: 52,
      blunders: 4,
      mistakes: 6,
      inaccuracies: 5,
      acpl: 88.4,
      accuracy: 76.3,
      wp_loss_per_game: 14.5,
    },
  ],
  by_color: [
    {
      key: 'white',
      label: 'As White',
      games: 2,
      moves: 44,
      blunders: 1,
      mistakes: 3,
      inaccuracies: 4,
      acpl: 58.2,
      accuracy: 84.1,
      wp_loss_per_game: 12.2,
    },
    {
      key: 'black',
      label: 'As Black',
      games: 2,
      moves: 48,
      blunders: 4,
      mistakes: 5,
      inaccuracies: 4,
      acpl: 70.1,
      accuracy: 80.7,
      wp_loss_per_game: 25.0,
    },
  ],
  by_opening: [
    {
      key: 'caro-kann-defense',
      label: 'Caro-Kann Defense',
      games: 3,
      moves: 30,
      blunders: 3,
      mistakes: 4,
      inaccuracies: 2,
      acpl: 96.3,
      accuracy: 74.9,
      wp_loss_per_game: 26.4,
    },
  ],
  top_moments: [
    {
      game_id: 'live:2',
      played_at: '2026-10-11T10:00:00Z',
      color: 'black',
      opponent: 'rival_2',
      move_number: 18,
      san: 'Qh5',
      classification: 'blunder',
      cp_loss: 640,
      wp_loss: 42.5,
      phase: 'middlegame',
      opening_name: 'Caro-Kann Defense',
      game_url: 'https://www.chess.com/game/live/2',
    },
    {
      game_id: 'live:3',
      played_at: '2026-10-12T10:00:00Z',
      color: 'white',
      opponent: 'rival_3',
      move_number: 9,
      san: 'Nf3',
      classification: 'mistake',
      cp_loss: 180,
      wp_loss: 12.3,
      phase: 'opening',
      opening_name: 'Sicilian Defense',
      game_url: 'https://www.chess.com/game/live/3',
    },
  ],
  primary_leak: {
    kind: 'opening',
    label: 'Caro-Kann Defense',
    wp_loss_per_game: 26.4,
    games: 3,
    moves: 30,
    blunders: 3,
    mistakes: 4,
  },
  ...meta,
};

export const analyzeScope: AnalyzeScope = {
  username: 'example_player',
  time_class: 'rapid',
  games_total: 5,
  already_analyzed: 4,
  queued: 1,
  pending: 1,
};
