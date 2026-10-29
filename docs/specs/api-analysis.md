# Engine analysis API and worker

Status: implemented. Code: `app/engine/` (`uci.py`, `game.py`, `accuracy.py`,
`profile.py`, `worker.py`), `app/services/analysis.py`, `app/schemas/analysis.py`,
`app/worker.py`, `app/models/analysis.py`, migration `0003`.

## Why asynchronous

Stockfish is CPU-bound: a single game takes seconds to tens of seconds. Running it inside
a request would tie up a worker thread and make latency unpredictable. The API therefore
only **enqueues** a durable job in PostgreSQL; a separate process
(`python -m app.worker`) claims jobs with `FOR UPDATE SKIP LOCKED`, analyses the game and
stores the result. No Redis or Celery is required.

```
POST /analysis ──> analysis_jobs (queued) ──> worker ──> game_analysis (payload)
GET  /analysis ──> cached payload or current job state
```

## Endpoints

Both endpoints accept only a game that belongs to the player's eligible dataset (same
rules as `api-games.md`: Rapid, standard chess, current 30-day window). An unknown or
ineligible game → `404 GAME_NOT_FOUND`.

### `POST /api/v1/players/{username}/games/{game_id}/analysis`

Idempotent. If a completed analysis exists for the current profile, it is returned
without creating a job. A `failed` job is reset to `queued` with `attempts = 0`; an
active (`queued` / `running`) job keeps its progress. A new job is created otherwise.

### `GET /api/v1/players/{username}/games/{game_id}/analysis`

Returns the current state. The frontend polls this while the status is `queued` or
`running`.

```json
{
  "username": "example_player",
  "game_id": "live:1",
  "status": "completed",
  "error_code": null,
  "requested_at": "2026-10-29T09:18:43Z",
  "completed_at": "2026-10-29T09:18:50Z",
  "analysis": {
    "schema_version": 1,
    "engine": { "name": "Stockfish", "version": "19", "depth": 12 },
    "players": { "white": "example_player", "black": "rival" },
    "result": "1-0",
    "moves": [
      {
        "ply": 1, "move_number": 1, "color": "white",
        "san": "e4", "uci": "e2e4",
        "eval_before_cp": 20, "eval_cp": 25, "mate": null,
        "best_move_uci": "e2e4", "best_move_san": "e4",
        "cp_loss": 0, "classification": "best"
      }
    ],
    "summary": {
      "white": { "accuracy": 84.98, "acpl": 50.12, "moves": 40, "counts": { "best": 17, "good": 16, "inaccuracy": 4, "mistake": 7, "blunder": 13 } },
      "black": { "accuracy": 86.19, "acpl": 45.3, "moves": 40, "counts": { "best": 0, "good": 0, "inaccuracy": 0, "mistake": 0, "blunder": 0 } }
    }
  }
}
```

`status`: `missing` (never requested) · `queued` · `running` · `completed` · `failed`.
`analysis` is `null` unless the status is `completed`. Evaluations are from **White's**
perspective; `cp_loss` and `classification` describe the move that was played.

## Error codes

| `error_code` | Meaning |
| ------------ | ------- |
| `missing_pgn` | The game has no PGN; it cannot be reviewed. |
| `malformed_pgn` | The PGN could not be parsed or contains an illegal move. |
| `no_moves` | The PGN has no moves. |
| `too_many_moves` | More than 400 plies (the analysis bound). |
| `ENGINE_UNAVAILABLE` | The worker could not start Stockfish. Retried. |
| `ENGINE_TIMEOUT` | A search exceeded `ANALYSIS_MOVE_TIMEOUT_SECONDS`. Retried. |
| `ENGINE_PROTOCOL_ERROR` | The engine produced invalid UCI output. Retried. |
| `WORKER_LOST` | A running job was abandoned and returned to the queue. |
| `GAME_DELETED` | The game disappeared before the worker ran. |
| `INTERNAL_ERROR` | Unexpected failure. Retried. |

A game that cannot be analysed fails **its own** job immediately and never affects other
games or requests. Engine failures are retried up to `ANALYSIS_JOB_MAX_ATTEMPTS` claims.

## Cache key

`profile_hash = SHA-256("chesspulse-analysis-v1|engine=stockfish|depth=…|threads=…|hash=…")`.
Changing depth, threads or hash size therefore produces new results instead of silently
reusing incomparable ones. The engine **version** is recorded in the payload but is not
part of the hash, because it is only known after the process starts.

## Metrics

Definitions are documented in `spec.md` §6.10 and `AGENT.md`:

- **Win probability**: logistic conversion of centipawns, capped at ±1000 cp.
- **Per-move accuracy**: `103.1668 * exp(-0.04354 * delta) - 3.1669`, clipped to 0–100,
  where `delta` is the mover's win-probability loss (published Lichess formula).
- **Game accuracy**: arithmetic mean of the player's per-move accuracies ("mean move
  accuracy" in the UI). It is not weighted by position difficulty.
- **CPL / ACPL**: `max(0, eval before - eval after)` from the mover's side, capped at
  1000 cp per move; ACPL is the mean.
- **Labels**: `best` (played the engine's top move), `good` (<50 cp), `inaccuracy`
  (50–99), `mistake` (100–199), `blunder` (≥200).

No rating is estimated from accuracy, and no label beyond these five is assigned.

## Worker

```bash
python -m app.worker            # poll forever
python -m app.worker --once     # one job
python -m app.worker --depth 14 # override the configured depth for this run
```

On startup the worker returns jobs left `running` for longer than
`ANALYSIS_STALE_JOB_MINUTES` to the queue (marked `WORKER_LOST`). Several workers may run
concurrently. `STOCKFISH_PATH` must point to a Stockfish binary, or `stockfish` must be on
`PATH`.
