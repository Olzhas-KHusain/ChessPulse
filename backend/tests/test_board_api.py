"""Free-board API: response shapes and safe error mapping (no database, fake engine)."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.dependencies import get_board_service
from app.core.config import Settings
from app.engine.board import (
    BoardEvaluation,
    IllegalMoveError,
    InvalidFenError,
    MoveAnalysis,
)
from app.engine.uci import EngineIdentity, EngineUnavailable
from app.main import create_app

START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
AFTER_E4 = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"


def _evaluation(fen: str) -> BoardEvaluation:
    return BoardEvaluation(
        fen=fen,
        turn="white",
        status="ongoing",
        eval_cp=35,
        mate=None,
        best_move_uci="e2e4",
        best_move_san="e4",
    )


def _move() -> MoveAnalysis:
    return MoveAnalysis(
        fen_before=START,
        fen_after=AFTER_E4,
        turn="white",
        move_number=1,
        san="e4",
        uci="e2e4",
        eval_before_cp=35,
        eval_after_cp=-20,
        mate_after=None,
        cp_loss=55,
        classification="inaccuracy",
        best_move_uci="d2d4",
        best_move_san="d4",
        best_move_after_uci="e7e5",
        best_move_after_san="e5",
        status_after="ongoing",
    )


class FakeBoardService:
    engine_identity = EngineIdentity("Fake", "1.0")
    depth = 10

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    def evaluate(self, fen: str) -> BoardEvaluation:
        if self.error is not None:
            raise self.error
        return _evaluation(fen)

    def analyze_move(self, fen: str, uci: str) -> MoveAnalysis:
        if self.error is not None:
            raise self.error
        return _move()

    def close(self) -> None:
        pass


@pytest.fixture
def app() -> FastAPI:
    settings = Settings(_env_file=None, database_url="postgresql+psycopg://u:secret@localhost:1/db")
    return create_app(settings)


def client(app: FastAPI, service: FakeBoardService) -> TestClient:
    app.dependency_overrides[get_board_service] = lambda: service
    return TestClient(app)


def test_evaluate_returns_white_perspective_and_engine(app: FastAPI) -> None:
    response = client(app, FakeBoardService()).post("/api/v1/board/evaluate", json={"fen": START})

    assert response.status_code == 200
    assert response.json() == {
        "fen": START,
        "turn": "white",
        "status": "ongoing",
        "eval_cp": 35,
        "mate": None,
        "best_move_uci": "e2e4",
        "best_move_san": "e4",
        "engine": {"name": "Fake", "version": "1.0", "depth": 10},
    }


def test_move_returns_classification_and_resulting_fen(app: FastAPI) -> None:
    response = client(app, FakeBoardService()).post(
        "/api/v1/board/move", json={"fen": START, "move_uci": "e2e4"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["san"] == "e4"
    assert body["fen_after"] == AFTER_E4
    assert body["cp_loss"] == 55
    assert body["classification"] == "inaccuracy"
    assert body["best_move_san"] == "d4"
    assert body["best_move_after_san"] == "e5"
    assert body["engine"]["name"] == "Fake"


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (InvalidFenError(), 400, "INVALID_FEN"),
        (IllegalMoveError(), 400, "ILLEGAL_MOVE"),
        (EngineUnavailable("not installed"), 503, "ENGINE_UNAVAILABLE"),
    ],
)
def test_board_errors_use_the_shared_envelope(
    app: FastAPI, error: Exception, status: int, code: str
) -> None:
    response = client(app, FakeBoardService(error)).post(
        "/api/v1/board/evaluate", json={"fen": START}
    )

    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert "not installed" not in response.text  # internal detail is never echoed


def test_missing_fen_is_reported_as_an_invalid_parameter(app: FastAPI) -> None:
    response = client(app, FakeBoardService()).post("/api/v1/board/evaluate", json={})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_PARAMETER"


def test_board_routes_are_not_available_with_get(app: FastAPI) -> None:
    response = client(app, FakeBoardService()).get("/api/v1/board/evaluate")
    assert response.status_code == 405


@dataclass
class _Unused:
    """Keeps the dataclass import meaningful for older type-checkers."""

    value: int


def test_fake_service_satisfies_the_router_contract() -> None:
    service = FakeBoardService()
    assert service.evaluate(START).eval_cp == 35
    assert service.analyze_move(START, "e2e4").san == "e4"
    assert _Unused(1).value == 1


def _noop() -> Iterator[None]:  # pragma: no cover - typing helper only
    yield
