"""Minimal, defensive UCI client for Stockfish.

The client speaks only the subset ChessPulse needs: handshake, fixed-depth
search of one position at a time, and a clean shutdown. Engine output is read on
a background thread so a hung engine becomes a timeout instead of a blocked
request or worker forever.

Scores returned here are **from the side to move**, exactly as UCI reports them;
normalization to White's perspective happens in :mod:`app.engine.game`.
"""

from __future__ import annotations

import contextlib
import queue
import subprocess
import threading
import time
from dataclasses import dataclass

_UCI_HANDSHAKE_TIMEOUT = 20.0
_READY_TIMEOUT = 20.0
_QUIT_TIMEOUT = 5.0


class EngineError(RuntimeError):
    """Base class for engine failures; ``code`` is safe to persist."""

    code = "ENGINE_ERROR"


class EngineUnavailable(EngineError):
    """The engine binary could not be started."""

    code = "ENGINE_UNAVAILABLE"


class EngineTimeout(EngineError):
    """The engine did not answer within the configured budget."""

    code = "ENGINE_TIMEOUT"


class EngineProtocolError(EngineError):
    """The engine answered with something that is not valid UCI output."""

    code = "ENGINE_PROTOCOL_ERROR"


@dataclass(frozen=True, slots=True)
class Evaluation:
    """Engine verdict for one position, from the side to move."""

    cp: int | None
    mate: int | None
    best_move: str | None

    @property
    def score_cp(self) -> int:
        """Centipawns for the side to move, with mate mapped to a large value.

        The magnitude of a mate score is capped deliberately: mate distance must
        not distort averages of ordinary evaluations.
        """
        if self.mate is not None:
            return 10_000 if self.mate > 0 else -10_000
        return self.cp or 0


@dataclass(frozen=True, slots=True)
class EngineIdentity:
    name: str
    version: str


def parse_identity(line: str) -> EngineIdentity | None:
    """Parse ``id name Stockfish 19`` into name and version.

    Returns ``None`` for other ``id`` lines. Engines that omit a version get
    ``"unknown"`` rather than an invented number.
    """
    if not line.startswith("id name "):
        return None
    raw = line[len("id name ") :].strip()
    if not raw:
        return None
    name, _, version = raw.rpartition(" ")
    if not name:
        return EngineIdentity(raw, "unknown")
    return EngineIdentity(name, version)


def parse_info(line: str) -> tuple[int | None, int | None, str | None]:
    """Extract ``(cp, mate, best_move)`` from one ``info`` line.

    Only the first ``pv`` move is returned; ``None`` values mean the line did not
    carry that piece of information.
    """
    tokens = line.split()
    cp: int | None = None
    mate: int | None = None
    best_move: str | None = None
    for index, token in enumerate(tokens):
        if token == "score" and index + 2 < len(tokens):
            kind, value = tokens[index + 1], tokens[index + 2]
            try:
                parsed = int(value)
            except ValueError:
                continue
            if kind == "cp":
                cp = parsed
            elif kind == "mate":
                mate = parsed
        elif token == "pv" and index + 1 < len(tokens):
            best_move = tokens[index + 1]
            break
    return cp, mate, best_move


class StockfishEngine:
    """One Stockfish process, reused for every position of a game."""

    def __init__(
        self,
        path: str,
        *,
        depth: int,
        threads: int = 1,
        hash_mb: int = 64,
        move_timeout_seconds: float = 30.0,
    ) -> None:
        self._path = path
        self._depth = depth
        self._threads = threads
        self._hash_mb = hash_mb
        self._move_timeout = move_timeout_seconds
        self._process: subprocess.Popen[str] | None = None
        self._lines: queue.Queue[str | None] = queue.Queue()
        self._reader: threading.Thread | None = None
        self._identity = EngineIdentity("Stockfish", "unknown")

    # -- lifecycle ---------------------------------------------------------

    @property
    def identity(self) -> EngineIdentity:
        return self._identity

    @property
    def depth(self) -> int:
        return self._depth

    def __enter__(self) -> StockfishEngine:
        self.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def start(self) -> None:
        if self._process is not None:
            return
        try:
            self._process = subprocess.Popen(
                [self._path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except OSError as exc:
            raise EngineUnavailable("could not start the engine") from exc

        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

        self._send("uci")
        self._await("uciok", _UCI_HANDSHAKE_TIMEOUT, EngineUnavailable)
        self._send(f"setoption name Threads value {self._threads}")
        self._send(f"setoption name Hash value {self._hash_mb}")
        self._send("setoption name MultiPV value 1")
        self._send("isready")
        self._await("readyok", _READY_TIMEOUT, EngineUnavailable)
        self._send("ucinewgame")

    def close(self) -> None:
        process = self._process
        if process is None:
            return
        self._process = None
        try:
            if process.poll() is None:
                process.stdin and process.stdin.write("quit\n")
                process.stdin and process.stdin.flush()
                process.wait(timeout=_QUIT_TIMEOUT)
        except (OSError, subprocess.TimeoutExpired):
            pass
        finally:
            if process.poll() is None:
                process.kill()
            for stream in (process.stdin, process.stdout):
                with contextlib.suppress(OSError):
                    stream and stream.close()

    def _read_loop(self) -> None:
        process = self._process
        if process is None or process.stdout is None:  # pragma: no cover - start() guards this
            return
        for line in process.stdout:
            self._lines.put(line.rstrip("\r\n"))
        self._lines.put(None)  # EOF marker: the process exited

    # -- protocol ----------------------------------------------------------

    def _send(self, command: str) -> None:
        process = self._process
        if process is None or process.stdin is None:
            raise EngineUnavailable("the engine is not running")
        try:
            process.stdin.write(command + "\n")
            process.stdin.flush()
        except OSError as exc:
            raise EngineUnavailable("the engine stopped accepting commands") from exc

    def _next_line(self, timeout: float, error: type[EngineError]) -> str:
        try:
            line = self._lines.get(timeout=timeout)
        except queue.Empty:
            raise EngineTimeout("the engine did not answer in time") from None
        if line is None:
            raise error("the engine process exited unexpectedly")
        return line

    def _await(self, expected: str, timeout: float, error: type[EngineError]) -> None:
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise EngineTimeout("the engine did not answer in time")
            line = self._next_line(remaining, error)
            if line.startswith("id name "):
                identity = parse_identity(line)
                if identity is not None:
                    self._identity = identity
            if line == expected:
                return

    def evaluate(self, fen: str) -> Evaluation:
        """Search ``fen`` to the configured depth and return the last verdict."""
        self._send(f"position fen {fen}")
        self._send(f"go depth {self._depth}")

        cp: int | None = None
        mate: int | None = None
        deadline = time.monotonic() + self._move_timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise EngineTimeout("the engine did not finish the search in time")
            line = self._next_line(remaining, EngineProtocolError)
            if line.startswith("bestmove"):
                tokens = line.split()
                return Evaluation(
                    cp=cp,
                    mate=mate,
                    best_move=tokens[1] if len(tokens) > 1 and tokens[1] != "(none)" else None,
                )
            if line.startswith("info") and " pv " in line:
                line_cp, line_mate, _ = parse_info(line)
                if line_cp is not None or line_mate is not None:
                    cp, mate = line_cp, line_mate
