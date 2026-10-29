"""Engine-analysis API and worker end to end (synthetic provider, fake engine)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.engine.uci import EngineIdentity, Evaluation
from app.engine.worker import run_once
from app.models import AnalysisJob, AnalysisJobStatus, GameAnalysis
from app.providers.types import ArchiveMonth
from tests.db.conftest import Client
from tests.ingestion_helpers import NOW, OWNER, FakeProvider, game

pytestmark = pytest.mark.integration

OCT = ArchiveMonth(2026, 10)
BASE = f"/api/v1/players/{OWNER}/games"
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
    return FakeProvider(
        months={OCT: [game(NOW - 5 * timedelta(days=1), game_id="live:1", pgn=GOOD_PGN)]}
    )


def _worker(session: Session, engine: Engine) -> bool:
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return run_once(factory, FakeEngine, max_attempts=3)


def test_analysis_request_is_queued_then_completed_and_cached(
    client: Client, session: Session, migrated_engine: Engine
) -> None:
    api = client(_provider())
    assert api.get(BASE).status_code == 200  # ingests the dataset
    url = f"{BASE}/live:1/analysis"

    missing = api.get(url).json()
    assert missing["status"] == "missing"

    queued = api.post(url).json()
    assert queued["status"] == "queued"
    assert queued["analysis"] is None

    # Requesting again does not create a second job.
    assert api.post(url).json()["status"] == "queued"
    assert session.scalar(select(func.count()).select_from(AnalysisJob)) == 1

    assert _worker(session, migrated_engine) is True

    done = api.get(url).json()
    assert done["status"] == "completed"
    assert done["analysis"]["engine"] == {"name": "Fake", "version": "1.0", "depth": 12}
    assert len(done["analysis"]["moves"]) == 4
    assert done["analysis"]["summary"]["white"]["accuracy"] == 100.0
    assert session.scalar(select(func.count()).select_from(GameAnalysis)) == 1

    # A completed analysis is returned by POST as well, without a new job.
    cached = api.post(url).json()
    assert cached["status"] == "completed"
    assert cached["analysis"]["moves"][0]["san"] == "e4"
    assert session.scalar(select(func.count()).select_from(AnalysisJob)) == 1


def test_unknown_game_has_no_analysis(client: Client) -> None:
    api = client(_provider())
    response = api.get(f"{BASE}/live:does-not-exist/analysis")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "GAME_NOT_FOUND"


def test_job_moves_to_failed_when_the_pgn_is_missing(
    client: Client, session: Session, migrated_engine: Engine
) -> None:
    provider = FakeProvider(
        months={OCT: [game(NOW - 5 * timedelta(days=1), game_id="live:1", pgn=None)]}
    )
    api = client(provider)
    assert api.get(BASE).status_code == 200
    url = f"{BASE}/live:1/analysis"
    assert api.post(url).json()["status"] == "queued"

    assert _worker(session, migrated_engine) is True

    body = api.get(url).json()
    assert body["status"] == "failed"
    assert body["error_code"] == "missing_pgn"
    job = session.scalar(select(AnalysisJob))
    assert job is not None and job.status is AnalysisJobStatus.FAILED
