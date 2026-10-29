"""Cross-game "form report": where a player's accuracy actually leaks.

This module is pure: it turns already-stored engine payloads into aggregates. It never
calls the engine and never touches the database, so the numbers are reproducible and
unit-testable.

Honesty rules:

* every aggregate is a sum or mean of engine values; nothing is inferred from results;
* the headline metric is **win probability lost per game** (percentage points), not an
  Elo estimate;
* phases are defined by move number, and the labels say so: opening (moves 1-10),
  middlegame (11-30), late (31+). They are not material-based endgame detection;
* a group is only eligible to be the "primary leak" with at least three analysed games,
  so one bad game cannot define the story.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.engine.accuracy import move_accuracy, win_percent

PHASE_OPENING = "opening"
PHASE_MIDDLEGAME = "middlegame"
PHASE_LATE = "late"
PHASE_LABELS = {
    PHASE_OPENING: "Opening (moves 1–10)",
    PHASE_MIDDLEGAME: "Middlegame (moves 11–30)",
    PHASE_LATE: "Late game (moves 31+)",
}
PHASE_ORDER = (PHASE_OPENING, PHASE_MIDDLEGAME, PHASE_LATE)

COLOR_LABELS = {"white": "As White", "black": "As Black"}
MIN_PRIMARY_GAMES = 3
MIN_OPENING_GAMES = 2
MAX_OPENINGS = 10
MAX_MOMENTS = 10
ACTIONABLE = ("inaccuracy", "mistake", "blunder")


@dataclass(frozen=True, slots=True)
class AnalysedGame:
    """One stored analysis plus the game metadata needed for grouping."""

    game_id: str
    played_at: datetime
    color: str
    result: str
    opponent: str
    opening_key: str | None
    opening_name: str | None
    game_url: str | None
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class GroupStats:
    key: str
    label: str
    games: int
    moves: int
    blunders: int
    mistakes: int
    inaccuracies: int
    acpl: float | None
    accuracy: float | None
    wp_loss_per_game: float


@dataclass(frozen=True, slots=True)
class AccuracyPoint:
    game_id: str
    played_at: datetime
    color: str
    result: str
    opponent: str
    accuracy: float | None
    acpl: float | None
    blunders: int
    mistakes: int


@dataclass(frozen=True, slots=True)
class Moment:
    game_id: str
    played_at: datetime
    color: str
    opponent: str
    move_number: int
    san: str
    classification: str
    cp_loss: int
    wp_loss: float
    phase: str
    opening_name: str | None
    game_url: str | None


@dataclass(frozen=True, slots=True)
class Leak:
    kind: str
    label: str
    wp_loss_per_game: float
    games: int
    moves: int
    blunders: int
    mistakes: int


@dataclass(frozen=True, slots=True)
class FormReport:
    games_analyzed: int
    accuracy_mean: float | None
    opponent_accuracy_mean: float | None
    acpl_mean: float | None
    wp_loss_per_game: float | None
    accuracy_trend: tuple[AccuracyPoint, ...]
    by_phase: tuple[GroupStats, ...]
    by_color: tuple[GroupStats, ...]
    by_opening: tuple[GroupStats, ...]
    top_moments: tuple[Moment, ...]
    primary_leak: Leak | None


@dataclass(slots=True)
class _Accumulator:
    key: str
    label: str
    games: set[int] = field(default_factory=set)
    moves: int = 0
    blunders: int = 0
    mistakes: int = 0
    inaccuracies: int = 0
    cp_loss_sum: int = 0
    wp_loss_sum: float = 0.0
    accuracy_sum: float = 0.0

    def add_move(self, *, game_index: int, move: dict[str, Any], wp_loss: float) -> None:
        self.games.add(game_index)
        self.moves += 1
        classification = move["classification"]
        if classification == "blunder":
            self.blunders += 1
        elif classification == "mistake":
            self.mistakes += 1
        elif classification == "inaccuracy":
            self.inaccuracies += 1
        self.cp_loss_sum += int(move["cp_loss"])
        self.wp_loss_sum += wp_loss
        before = wp_loss_before(move)
        self.accuracy_sum += move_accuracy(before, max(0.0, before - wp_loss))

    def stats(self) -> GroupStats:
        games = len(self.games)
        return GroupStats(
            key=self.key,
            label=self.label,
            games=games,
            moves=self.moves,
            blunders=self.blunders,
            mistakes=self.mistakes,
            inaccuracies=self.inaccuracies,
            acpl=_mean(self.cp_loss_sum, self.moves),
            accuracy=_mean(self.accuracy_sum, self.moves),
            wp_loss_per_game=round(self.wp_loss_sum / games, 2) if games else 0.0,
        )


def wp_loss_before(move: dict[str, Any]) -> float:
    """Win probability the mover had before the move, from the mover's side."""
    before = win_percent(int(move["eval_before_cp"]))
    return before if move["color"] == "white" else 100.0 - before


def move_wp_loss(move: dict[str, Any]) -> float:
    """Win probability (percentage points) the mover gave up with this move."""
    before = win_percent(int(move["eval_before_cp"]))
    after = win_percent(int(move["eval_cp"]))
    if move["color"] == "black":
        before, after = 100.0 - before, 100.0 - after
    return max(0.0, before - after)


def phase_for(move_number: int) -> str:
    if move_number <= 10:
        return PHASE_OPENING
    if move_number <= 30:
        return PHASE_MIDDLEGAME
    return PHASE_LATE


def _mean(total: float, count: int) -> float | None:
    return round(total / count, 2) if count else None


def build_form_report(games: list[AnalysedGame]) -> FormReport:
    """Aggregate analysed games into a form report. ``games`` may be empty."""
    phases = {key: _Accumulator(key, PHASE_LABELS[key]) for key in PHASE_ORDER}
    colors = {key: _Accumulator(key, label) for key, label in COLOR_LABELS.items()}
    openings: dict[str, _Accumulator] = {}

    trend: list[AccuracyPoint] = []
    moments: list[Moment] = []
    own_accuracy: list[float] = []
    rival_accuracy: list[float] = []
    own_acpl: list[float] = []
    total_wp_loss = 0.0

    for index, game in enumerate(games):
        payload = game.payload
        summary = payload.get("summary", {}).get(game.color, {})
        accuracy = summary.get("accuracy")
        acpl = summary.get("acpl")
        if accuracy is not None:
            own_accuracy.append(float(accuracy))
        if acpl is not None:
            own_acpl.append(float(acpl))
        rival = payload.get("summary", {}).get("black" if game.color == "white" else "white", {})
        if rival.get("accuracy") is not None:
            rival_accuracy.append(float(rival["accuracy"]))

        counts = summary.get("counts", {})
        trend.append(
            AccuracyPoint(
                game_id=game.game_id,
                played_at=game.played_at,
                color=game.color,
                result=game.result,
                opponent=game.opponent,
                accuracy=accuracy,
                acpl=acpl,
                blunders=int(counts.get("blunder", 0)),
                mistakes=int(counts.get("mistake", 0)),
            )
        )

        opening_key = game.opening_key or "unknown"
        opening_label = game.opening_name or "Unknown opening"
        opening = openings.setdefault(opening_key, _Accumulator(opening_key, opening_label))

        for move in payload.get("moves", []):
            if move.get("color") != game.color:
                continue
            if "eval_before_cp" not in move or "eval_cp" not in move:
                continue
            loss = move_wp_loss(move)
            total_wp_loss += loss
            phase = phase_for(int(move["move_number"]))
            phases[phase].add_move(game_index=index, move=move, wp_loss=loss)
            colors[game.color].add_move(game_index=index, move=move, wp_loss=loss)
            opening.add_move(game_index=index, move=move, wp_loss=loss)
            if move["classification"] in ACTIONABLE:
                moments.append(
                    Moment(
                        game_id=game.game_id,
                        played_at=game.played_at,
                        color=game.color,
                        opponent=game.opponent,
                        move_number=int(move["move_number"]),
                        san=str(move["san"]),
                        classification=str(move["classification"]),
                        cp_loss=int(move["cp_loss"]),
                        wp_loss=round(loss, 2),
                        phase=phase,
                        opening_name=game.opening_name,
                        game_url=game.game_url,
                    )
                )

    analysed = len(games)
    phase_stats = [phases[key].stats() for key in PHASE_ORDER]
    color_stats = [colors[key].stats() for key in COLOR_LABELS]
    opening_stats = sorted(
        (item.stats() for item in openings.values() if len(item.games) >= MIN_OPENING_GAMES),
        key=lambda item: (-item.wp_loss_per_game, -item.blunders, item.label),
    )[:MAX_OPENINGS]
    moments.sort(key=lambda item: -item.wp_loss)

    trend.sort(key=lambda point: point.played_at)
    return FormReport(
        games_analyzed=analysed,
        accuracy_mean=_mean(sum(own_accuracy), len(own_accuracy)),
        opponent_accuracy_mean=_mean(sum(rival_accuracy), len(rival_accuracy)),
        acpl_mean=_mean(sum(own_acpl), len(own_acpl)),
        wp_loss_per_game=round(total_wp_loss / analysed, 2) if analysed else None,
        accuracy_trend=tuple(trend),
        by_phase=tuple(phase_stats),
        by_color=tuple(color_stats),
        by_opening=tuple(opening_stats),
        top_moments=tuple(moments[:MAX_MOMENTS]),
        primary_leak=_primary_leak(phase_stats, color_stats, opening_stats),
    )


def _primary_leak(
    phases: list[GroupStats], colors: list[GroupStats], openings: list[GroupStats]
) -> Leak | None:
    candidates = [("opening", item) for item in openings if item.games >= MIN_PRIMARY_GAMES]
    candidates += [("phase", item) for item in phases if item.games >= MIN_PRIMARY_GAMES]
    candidates += [("color", item) for item in colors if item.games >= MIN_PRIMARY_GAMES]
    if not candidates:
        return None
    kind, best = max(
        candidates,
        key=lambda pair: (
            pair[1].wp_loss_per_game,
            pair[1].blunders + pair[1].mistakes,
            pair[1].moves,
        ),
    )
    if best.wp_loss_per_game <= 0:
        return None
    return Leak(
        kind=kind,
        label=best.label,
        wp_loss_per_game=best.wp_loss_per_game,
        games=best.games,
        moves=best.moves,
        blunders=best.blunders,
        mistakes=best.mistakes,
    )
