# Free board API

Status: implemented. Code: `app/engine/board.py` (pure position logic),
`app/services/board.py` (locked Stockfish service), `app/engine/runtime.py` (engine
identity), `app/schemas/board.py`, `app/api/v1/routers/board.py`, `app/api/v1/errors.py`.

The free board is independent of the player dataset: it never touches the database, the
cache or the analysis queue. Both endpoints run the same Stockfish binary and the same
evaluation helpers as `api-analysis.md`, synchronously, for one position. The engine
identity and depth are returned with every response so the UI can state what produced
the verdict.

Scores are always **from White's perspective** (`eval_cp`, `mate`). `cp_loss` and
`classification` are **from the mover's perspective**.

## Engine identity

| Field     | Meaning                                                        |
| --------- | -------------------------------------------------------------- |
| `name`    | Engine name reported by UCI (`Stockfish`).                     |
| `version` | Engine version (for example `16.0`).                           |
| `depth`   | Fixed search depth from `ANALYSIS_DEPTH` (default 12).          |

A mate score is exposed as `eval_cp = ±10000` and a non-null `mate` (positive = White
mates). A position that is already decided (checkmate, stalemate, insufficient
material, seventy-five-move rule, fivefold repetition) is returned without an engine
search.

## `POST /api/v1/board/evaluate`

Request:

```json
{ "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1" }
```

`fen` is required, 1–128 characters, and must be a legal chess position (both kings,
side not to move not in check, at most eight pawns per side, and so on).

Response `200`:

```json
{
  "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
  "turn": "white",
  "status": "ongoing",
  "eval_cp": 32,
  "mate": null,
  "best_move_uci": "e2e4",
  "best_move_san": "e4",
  "engine": { "name": "Stockfish", "version": "16.0", "depth": 12 }
}
```

| Field           | Type                                                        |
| --------------- | ----------------------------------------------------------- |
| `fen`           | Echo of the validated position.                             |
| `turn`          | `white` / `black` — the side to move.                       |
| `status`        | `ongoing`, `checkmate`, `stalemate`, `insufficient_material`, `seventyfive_moves`, `fivefold_repetition`. |
| `eval_cp`       | Centipawns, White-relative; mates use ±10000.               |
| `mate`          | Mate distance, White-relative; `null` when not a mate.      |
| `best_move_uci` | Engine's best move, or `null` when the game is over.        |
| `best_move_san` | The same move in SAN.                                       |
| `engine`        | Engine identity (see above).                                |

## `POST /api/v1/board/move`

Request:

```json
{ "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1", "move_uci": "e2e4" }
```

`move_uci` is a legal move in UCI notation (4 characters, or 5 with a promotion piece).
The position before the move must be valid.

Response `200`:

```json
{
  "fen_before": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
  "fen_after": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
  "turn": "white",
  "move_number": 1,
  "san": "e4",
  "uci": "e2e4",
  "eval_before_cp": 30,
  "eval_after_cp": 31,
  "mate_after": null,
  "cp_loss": 0,
  "classification": "best",
  "best_move_uci": "e2e4",
  "best_move_san": "e4",
  "best_move_after_uci": "c7c5",
  "best_move_after_san": "c5",
  "status_after": "ongoing",
  "engine": { "name": "Stockfish", "version": "16.0", "depth": 12 }
}
```

| Field                 | Type / meaning                                                              |
| --------------------- | --------------------------------------------------------------------------- |
| `fen_before`          | Position before the move.                                                   |
| `fen_after`           | Position after the move (en passant target preserved).                      |
| `turn`                | The side that played the move.                                              |
| `move_number`         | Full-move number before the move (1 for White's first move).                |
| `san` / `uci`         | The played move in both notations.                                          |
| `eval_before_cp`      | White-relative evaluation before the move.                                  |
| `eval_after_cp`       | White-relative evaluation after the move.                                   |
| `mate_after`          | Mate distance after the move, White-relative.                               |
| `cp_loss`             | Centipawn loss from the mover's perspective, capped at 1000.                |
| `classification`      | `best`, `good`, `inaccuracy`, `mistake`, `blunder` (same thresholds as `api-analysis.md`). |
| `best_move_uci/san`   | Engine's best move in the position before the played move.                  |
| `best_move_after_uci/san` | Engine's best move in the resulting position, so the UI needs no extra call. |
| `status_after`        | Status of the resulting position.                                           |
| `engine`              | Engine identity.                                                            |

## Errors

Uses the error envelope from `api-overview.md`:

```json
{ "error": { "code": "INVALID_FEN", "message": "The position is not a valid chess position." } }
```

| Status | Code                    | When                                                        |
| ------ | ----------------------- | ----------------------------------------------------------- |
| `400`  | `INVALID_FEN`           | The FEN is malformed or not a legal position.               |
| `400`  | `ILLEGAL_MOVE`          | `move_uci` is not legal in the given position.              |
| `400`  | `INVALID_PARAMETER`     | A field is missing or outside its length limits.            |
| `502`  | `ENGINE_PROTOCOL_ERROR` | Stockfish returned an unusable response.                    |
| `503`  | `ENGINE_UNAVAILABLE`    | The binary is missing or cannot be started.                 |
| `504`  | `ENGINE_TIMEOUT`        | The search did not finish within the configured timeout.    |

Error messages never echo the submitted FEN or move.
