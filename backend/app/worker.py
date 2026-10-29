"""Engine-analysis worker process.

Usage::

    python -m app.worker            # loop forever, polling the queue
    python -m app.worker --once     # process at most one job and exit
    python -m app.worker --depth 14 # override the configured depth for this run

The worker is a separate process on purpose: Stockfish is CPU-bound, and keeping
it out of the API process means a long search never delays a request.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

from app.core.config import Settings, load_settings
from app.core.logging import configure_logging
from app.db.session import build_engine, build_session_factory
from app.engine.uci import EngineUnavailable, StockfishEngine
from app.engine.worker import requeue_stale_jobs, run_once


def resolve_engine_path(settings: Settings) -> str:
    """Return a usable Stockfish executable path or raise :class:`EngineUnavailable`."""
    candidate = settings.stockfish_path.strip() or (shutil.which("stockfish") or "")
    if not candidate or not Path(candidate).is_file():
        raise EngineUnavailable(
            "Stockfish was not found. Install it (winget install Stockfish.Stockfish) "
            "or set STOCKFISH_PATH to the executable."
        )
    return candidate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.worker")
    parser.add_argument("--once", action="store_true", help="process at most one job")
    parser.add_argument("--depth", type=int, help="override the configured search depth")
    parser.add_argument(
        "--poll", type=float, help="seconds between empty-queue polls (default: configured)"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = load_settings()
    except Exception as exc:  # ConfigurationError carries a safe message
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2

    if args.depth is not None:
        settings = settings.model_copy(update={"analysis_depth": args.depth})
    poll_seconds = args.poll if args.poll is not None else settings.analysis_worker_poll_seconds

    configure_logging(settings.log_level)
    try:
        engine_path = resolve_engine_path(settings)
    except EngineUnavailable as exc:
        print(str(exc), file=sys.stderr)
        return 2

    engine = build_engine(settings)
    session_factory = build_session_factory(engine)

    def engine_factory() -> StockfishEngine:
        return StockfishEngine(
            engine_path,
            depth=settings.analysis_depth,
            threads=settings.analysis_threads,
            hash_mb=settings.analysis_hash_mb,
            move_timeout_seconds=settings.analysis_move_timeout_seconds,
        )

    with session_factory() as session:
        requeued = requeue_stale_jobs(session, settings.analysis_stale_job_minutes)
    if requeued:
        print(f"requeued {requeued} stale job(s)")

    try:
        while True:
            worked = run_once(
                session_factory,
                engine_factory,
                max_attempts=settings.analysis_job_max_attempts,
            )
            if args.once:
                return 0
            if not worked:
                time.sleep(poll_seconds)
    except KeyboardInterrupt:
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
