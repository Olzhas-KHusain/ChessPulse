"""Cross-game form aggregation (pure, no engine, no database)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.analytics.form import (
    PHASE_LATE,
    PHASE_MIDDLEGAME,
    PHASE_OPENING,
    AnalysedGame,
    build_form_report,
    phase_for,
)

T0 = datetime(2026, 10, 1, 12, tzinfo=UTC)


def move(
    *,
    color: str,
    move_number: int,
    san: str = "e4",
    eval_before_cp: int = 0,
    eval_cp: int = 0,
    cp_loss: int = 0,
    classification: str = "best",
) -> dict[str, Any]:
    return {
        "color": color,
        "move_number": move_number,
        "san": san,
        "eval_before_cp": eval_before_cp,
        "eval_cp": eval_cp,
        "cp_loss": cp_loss,
        "classification": classification,
    }


def payload(
    *,
    color: str,
    moves: list[dict[str, Any]],
    accuracy: float = 80.0,
    acpl: float = 40.0,
    counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    rival = "black" if color == "white" else "white"
    own_counts = counts or {"best": 0, "good": 0, "inaccuracy": 0, "mistake": 0, "blunder": 0}
    return {
        "schema_version": 1,
        "engine": {"name": "Stockfish", "version": "19", "depth": 12},
        "summary": {
            color: {"accuracy": accuracy, "acpl": acpl, "moves": len(moves), "counts": own_counts},
            rival: {
                "accuracy": 70.0,
                "acpl": 60.0,
                "moves": 1,
                "counts": {"best": 0, "good": 0, "inaccuracy": 0, "mistake": 0, "blunder": 0},
            },
        },
        "moves": moves,
    }


def game(
    index: int,
    *,
    color: str = "white",
    moves: list[dict[str, Any]],
    opening_key: str | None = "caro-kann-defense",
    opening_name: str | None = "Caro-Kann Defense",
    result: str = "win",
) -> AnalysedGame:
    return AnalysedGame(
        game_id=f"live:{index}",
        played_at=T0 + timedelta(hours=index),
        color=color,
        result=result,
        opponent=f"rival_{index}",
        opening_key=opening_key,
        opening_name=opening_name,
        game_url=f"https://www.chess.com/game/live/{index}",
        payload=payload(color=color, moves=moves),
    )


def test_empty_report_has_no_numbers() -> None:
    report = build_form_report([])
    assert report.games_analyzed == 0
    assert report.accuracy_mean is None
    assert report.acpl_mean is None
    assert report.wp_loss_per_game is None
    assert report.primary_leak is None
    assert report.top_moments == ()
    assert [group.key for group in report.by_phase] == [PHASE_OPENING, PHASE_MIDDLEGAME, PHASE_LATE]


def test_phase_boundaries_are_by_move_number() -> None:
    assert phase_for(1) == PHASE_OPENING
    assert phase_for(10) == PHASE_OPENING
    assert phase_for(11) == PHASE_MIDDLEGAME
    assert phase_for(30) == PHASE_MIDDLEGAME
    assert phase_for(31) == PHASE_LATE


def test_best_moves_do_not_create_a_leak() -> None:
    report = build_form_report(
        [
            game(1, moves=[move(color="white", move_number=1)]),
            game(2, moves=[move(color="white", move_number=2)]),
            game(3, moves=[move(color="white", move_number=3)]),
        ]
    )
    assert report.games_analyzed == 3
    assert report.wp_loss_per_game == 0.0
    assert report.primary_leak is None
    assert report.by_phase[0].accuracy == 100.0
    assert report.by_phase[0].games == 3


def test_primary_leak_is_the_phase_with_the_largest_loss_per_game() -> None:
    opening_blunder = move(
        color="white",
        move_number=5,
        eval_before_cp=0,
        eval_cp=-900,
        cp_loss=900,
        classification="blunder",
    )
    late_slip = move(
        color="white",
        move_number=40,
        eval_before_cp=0,
        eval_cp=-100,
        cp_loss=100,
        classification="mistake",
    )
    report = build_form_report(
        [
            game(1, moves=[opening_blunder, late_slip]),
            game(2, moves=[opening_blunder, late_slip]),
            game(3, moves=[opening_blunder, late_slip]),
        ]
    )

    by_phase = {group.key: group for group in report.by_phase}
    assert by_phase[PHASE_OPENING].wp_loss_per_game > by_phase[PHASE_LATE].wp_loss_per_game
    assert by_phase[PHASE_OPENING].blunders == 3
    assert by_phase[PHASE_LATE].mistakes == 3
    assert report.primary_leak is not None
    assert report.primary_leak.kind in {"phase", "opening"}
    assert report.primary_leak.blunders == 3


def test_loss_per_game_is_normalised_by_analysed_games_not_moves() -> None:
    blunder = move(
        color="white",
        move_number=5,
        eval_before_cp=0,
        eval_cp=-500,
        cp_loss=500,
        classification="blunder",
    )
    one = build_form_report([game(1, moves=[blunder])])
    two = build_form_report([game(1, moves=[blunder]), game(2, moves=[])])
    assert one.wp_loss_per_game is not None and two.wp_loss_per_game is not None
    assert one.wp_loss_per_game == pytest.approx(two.wp_loss_per_game * 2, abs=0.02)


def test_moments_are_ranked_and_exclude_good_moves() -> None:
    moves = [
        move(
            color="white",
            move_number=4,
            san="Nf3",
            eval_before_cp=0,
            eval_cp=-50,
            cp_loss=50,
            classification="inaccuracy",
        ),
        move(
            color="white",
            move_number=8,
            san="Qh5",
            eval_before_cp=0,
            eval_cp=-800,
            cp_loss=800,
            classification="blunder",
        ),
        move(color="white", move_number=9, san="Be2", classification="good"),
        move(
            color="black",
            move_number=10,
            san="Nc6",
            eval_before_cp=0,
            eval_cp=-900,
            cp_loss=900,
            classification="blunder",
        ),
    ]
    report = build_form_report([game(1, color="white", moves=moves)])
    assert [moment.san for moment in report.top_moments] == ["Qh5", "Nf3"]
    assert report.top_moments[0].phase == PHASE_OPENING
    assert report.top_moments[0].game_url == "https://www.chess.com/game/live/1"


def test_black_moves_are_evaluated_from_black_perspective() -> None:
    # White's evaluation drops from +200 to -300, so Black gains; this is not a leak.
    winning_for_black = move(
        color="black",
        move_number=5,
        eval_before_cp=200,
        eval_cp=-300,
        cp_loss=0,
        classification="best",
    )
    report = build_form_report([game(1, color="black", moves=[winning_for_black])])
    assert report.wp_loss_per_game == 0.0
    assert report.top_moments == ()


def test_openings_need_two_games_and_are_sorted_by_loss() -> None:
    blunder = move(
        color="white",
        move_number=5,
        eval_before_cp=0,
        eval_cp=-600,
        cp_loss=600,
        classification="blunder",
    )
    quiet = move(color="white", move_number=5)
    games = [
        game(1, moves=[blunder], opening_key="sicilian", opening_name="Sicilian Defense"),
        game(2, moves=[blunder], opening_key="sicilian", opening_name="Sicilian Defense"),
        game(3, moves=[quiet], opening_key="french", opening_name="French Defense"),
        game(4, moves=[blunder], opening_key="rare", opening_name="Rare Opening"),
    ]
    report = build_form_report(games)
    keys = [group.key for group in report.by_opening]
    assert keys == ["sicilian"]
    assert report.by_opening[0].games == 2
    assert report.by_opening[0].wp_loss_per_game > 0


def test_colour_split_and_opponent_accuracy_mean() -> None:
    report = build_form_report(
        [
            game(1, color="white", moves=[move(color="white", move_number=1)]),
            game(2, color="black", moves=[move(color="black", move_number=1)]),
        ]
    )
    by_color = {group.key: group for group in report.by_color}
    assert by_color["white"].games == 1
    assert by_color["black"].games == 1
    assert report.accuracy_mean == 80.0
    assert report.opponent_accuracy_mean == 70.0
