"""Form report API end to end (synthetic provider, fake engine, PostgreSQL)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.engine.uci import EngineIdentity, Evaluation
from app.engine.worker import run_once
from app.providers.types import ArchiveMonth
from tests.db.conftest import Client
from tests.ingestion_helpers import NOW, OWNER, FakeProvider, game

pytestmark = pytest.mark.integration

OCT = ArchiveMonth(2026, 10)
BASE = f"/api/v1/players/{OWNER}"
GOOD_PGN = (
    '[Event "Live Chess"]\n[White "example_player"]\n[Black "rival"]\n'
    '[Result "1-0"]\n\n1. e4 e5 2. Nf3 Nc6 1-0\n'
)


class FakeEngine:
    identity = EngineIdentity("Fake", "1.0")
    depth = 12

    def evaluate(self, fen: str) -> Evaluation:
        return Evaluation(cp=0, mate=None, best_move=None)

    def __enter__(self) -> FakeEngine:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


def _provider() -> FakeProvider:
    games = [
        game(
            NOW - timedelta(days=5),
            game_id=f"live:{index}",
            pgn=GOOD_PGN,
            opponent=f"rival_{index}",
        )
        for index in (1, 2)
    ]
    return FakeProvider(months={OCT: games})


def _run_worker(engine: Engine) -> None:
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    while run_once(factory, FakeEngine, max_attempts=3):
        pass


def test_form_report_starts_empty_then_aggregates_analysed_games(
    client: Client, session: Session, migrated_engine: Engine
) -> None:
    api = client(_provider())
    assert api.get(f"{BASE}/overview").status_code == 200  # ingests the dataset

    empty = api.get(f"{BASE}/form").json()
    assert empty["games_total"] == 2
    assert empty["games_analyzed"] == 0
    assert empty["accuracy_mean"] is None
    assert empty["primary_leak"] is None
    assert empty["accuracy_trend"] == []

    queued = api.post(f"{BASE}/form/analyze").json()
    assert queued["games_total"] == 2
    assert queued["already_analyzed"] == 0
    assert queued["queued"] == 2
    assert queued["pending"] == 2

    _run_worker(migrated_engine)

    report = api.get(f"{BASE}/form").json()
    assert report["games_total"] == 2
    assert report["games_analyzed"] == 2
    assert report["games_queued"] == 0
    assert report["games_failed"] == 0
    assert report["accuracy_mean"] == 100.0
    assert report["wp_loss_per_game"] == 0.0
    assert report["primary_leak"] is None
    assert [point["game_id"] for point in report["accuracy_trend"]] == ["live:1", "live:2"]
    assert report["by_phase"][0]["games"] == 2
    assert report["by_phase"][0]["moves"] == 4

    # A second request only reports the already analysed games.
    again = api.post(f"{BASE}/form/analyze").json()
    assert again["queued"] == 0
    assert again["already_analyzed"] == 2
    assert again["pending"] == 0
