"""Long-lived Stockfish service for the free analysis board.

A single engine process is started lazily on the first request and reused. The UCI
client is not thread-safe, so a lock serializes searches; the free board is an
interactive, single-user tool and does not need parallel engine calls.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from contextlib import AbstractContextManager

from app.engine.board import (
    BoardEvaluation,
    MoveAnalysis,
    evaluate_fen,
)
from app.engine.board import (
    analyze_move as analyze_board_move,
)
from app.engine.game import Engine
from app.engine.uci import EngineIdentity


class BoardAnalysisService:
    def __init__(self, engine_factory: Callable[[], AbstractContextManager[Engine]]) -> None:
        self._factory = engine_factory
        self._context: AbstractContextManager[Engine] | None = None
        self._engine: Engine | None = None
        self._lock = threading.Lock()

    def _engine_or_start(self) -> Engine:
        if self._engine is None:
            self._context = self._factory()
            self._engine = self._context.__enter__()
        return self._engine

    def evaluate(self, fen: str) -> BoardEvaluation:
        with self._lock:
            return evaluate_fen(fen, self._engine_or_start())

    def analyze_move(self, fen: str, uci: str) -> MoveAnalysis:
        with self._lock:
            return analyze_board_move(fen, uci, self._engine_or_start())

    @property
    def engine_identity(self) -> EngineIdentity:
        with self._lock:
            return self._engine_or_start().identity

    @property
    def depth(self) -> int:
        with self._lock:
            return self._engine_or_start().depth

    def close(self) -> None:
        with self._lock:
            if self._context is not None:
                self._context.__exit__(None, None, None)
                self._context = None
                self._engine = None
