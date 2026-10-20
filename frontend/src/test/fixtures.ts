/** Synthetic API responses for component tests (shapes match docs/specs/api-*.md). */
import type {
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
