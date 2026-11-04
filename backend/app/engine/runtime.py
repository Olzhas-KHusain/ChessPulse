"""Locate and construct the Stockfish process used by the API and the worker."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

from app.core.config import Settings
from app.engine.uci import EngineUnavailable, StockfishEngine


def resolve_engine_path(settings: Settings) -> str:
    """Return a usable Stockfish executable path or raise :class:`EngineUnavailable`."""
    candidate = settings.stockfish_path.strip() or (shutil.which("stockfish") or "")
    if not candidate or not Path(candidate).is_file():
        raise EngineUnavailable(
            "Stockfish was not found. Install it (winget install Stockfish.Stockfish) "
            "or set STOCKFISH_PATH to the executable."
        )
    return candidate


def stockfish_factory(settings: Settings) -> Callable[[], StockfishEngine]:
    """A zero-argument factory; the path is resolved when the engine is first used."""

    def factory() -> StockfishEngine:
        return StockfishEngine(
            resolve_engine_path(settings),
            depth=settings.analysis_depth,
            threads=settings.analysis_threads,
            hash_mb=settings.analysis_hash_mb,
            move_timeout_seconds=settings.analysis_move_timeout_seconds,
        )

    return factory
