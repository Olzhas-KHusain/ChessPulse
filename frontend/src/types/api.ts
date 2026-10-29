/**
 * Types mirroring the backend response schemas (docs/specs/api-*.md).
 * `null` always means "not available" and must never be rendered as 0.
 */

export type DataStatus = 'fresh' | 'partial' | 'stale';
export type PlayerOutcome = 'win' | 'loss' | 'draw' | 'unknown';
export type GroupSort = 'games' | 'win_rate' | 'name';

export interface Period {
  start: string;
  end: string;
  timezone: 'UTC';
}

export interface DatasetMeta {
  data_status: DataStatus;
  refresh_error: string | null;
  as_of: string;
  last_successful_update: string;
}

export interface Streak {
  type: 'win' | 'loss' | 'draw';
  length: number;
}

export interface CurrentRating {
  rating: number;
  as_of: string | null;
  source: 'provider_stats';
}

export interface Overview {
  username: string;
  period: Period;
  games_count: number;
  wins: number;
  losses: number;
  draws: number;
  unknown_results: number;
  win_rate: number | null;
  current_rating: number | null;
  current_rating_detail: CurrentRating | null;
  current_streak: Streak | null;
  longest_winning_streak: number | null;
  streak_may_be_incomplete: boolean;
  data_status: DataStatus;
  missing_sections: string[];
  refresh_error: string | null;
  as_of: string;
  last_successful_update: string;
}

export interface RatingPoint {
  timestamp: string;
  rating: number;
  source: 'game_record';
  game_id: number;
}

export interface RatingHistory extends DatasetMeta {
  username: string;
  period: Period;
  points: RatingPoint[];
  rating_semantics: 'reported_with_game';
  coverage: 'complete' | 'partial' | 'none';
  games_considered: number;
  games_without_rating: number;
  duplicates_removed: number;
}

export interface GroupStats {
  games_count: number;
  wins: number;
  losses: number;
  draws: number;
  unknown_results: number;
  win_rate: number | null;
}

export interface OpeningItem extends GroupStats {
  opening_key: string | null;
  name: string;
  eco_code: string | null;
  is_unknown: boolean;
}

export interface Openings extends DatasetMeta {
  username: string;
  period: Period;
  sort: GroupSort;
  total_groups: number;
  items: OpeningItem[];
}

export interface OpponentItem extends GroupStats {
  opponent_username: string;
  profile_url: string;
  last_played_at: string;
  last_rating: number | null;
}

export interface Opponents extends DatasetMeta {
  username: string;
  period: Period;
  perspective: 'searched_player';
  sort: GroupSort;
  total_groups: number;
  items: OpponentItem[];
}

export interface GameSummary {
  game_id: string;
  played_at: string;
  result: PlayerOutcome;
  color: 'white' | 'black';
  player_rating: number | null;
  opponent: { username: string; rating: number | null };
  time_control: string | null;
  rated: boolean | null;
  opening: { opening_key: string; name: string; eco_code: string | null } | null;
  game_url: string | null;
}

export interface GameList extends DatasetMeta {
  username: string;
  period: Period;
  result_filter: PlayerOutcome | null;
  items: GameSummary[];
  next_cursor: string | null;
}

export interface GameDetail extends DatasetMeta {
  username: string;
  game: GameSummary;
  rating_semantics: 'reported_with_game';
  pgn: {
    status: 'available' | 'missing' | 'malformed';
    headers: Record<string, string>;
    moves_san: string[] | null;
    error: string | null;
    raw: string | null;
  };
}

export interface ApiErrorBody {
  error: { code: string; message: string; request_id: string };
}

export type MoveClassification = 'best' | 'good' | 'inaccuracy' | 'mistake' | 'blunder';

export interface AnalysedMove {
  ply: number;
  move_number: number;
  color: 'white' | 'black';
  san: string;
  uci: string;
  eval_before_cp: number;
  eval_cp: number;
  mate: number | null;
  best_move_uci: string | null;
  best_move_san: string | null;
  cp_loss: number;
  classification: MoveClassification;
}

export interface PlayerAnalysisSummary {
  accuracy: number | null;
  acpl: number | null;
  moves: number;
  counts: Record<MoveClassification, number>;
}

export interface GameAnalysisPayload {
  schema_version: number;
  engine: { name: string; version: string; depth: number };
  players: Record<string, string>;
  result: string;
  moves: AnalysedMove[];
  summary: Record<'white' | 'black', PlayerAnalysisSummary>;
}

export interface AnalysisState {
  username: string;
  game_id: string;
  status: 'missing' | 'queued' | 'running' | 'completed' | 'failed';
  error_code: string | null;
  requested_at: string | null;
  completed_at: string | null;
  analysis: GameAnalysisPayload | null;
}
