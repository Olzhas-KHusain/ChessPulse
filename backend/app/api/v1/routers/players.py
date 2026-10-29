"""Player endpoints under ``/api/v1``. HTTP concerns only; logic lives in services."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.analytics.breakdowns import GroupSort
from app.api.v1.dependencies import get_now, get_provider, get_session, get_settings_dep
from app.cache.service import PlayerDatasetCache
from app.core.config import Settings
from app.models import PlayerResult
from app.providers.base import GameDataProvider
from app.schemas.analysis import AnalysisStateResponse
from app.schemas.breakdowns import OpeningsResponse, OpponentsResponse, RatingHistoryResponse
from app.schemas.form import AnalyzeScopeResponse, FormReportResponse
from app.schemas.games import GameDetailResponse, GameListResponse
from app.schemas.overview import ErrorResponse, OverviewResponse
from app.services.analysis import AnalysisService
from app.services.breakdowns import MAX_LIMIT, BreakdownService
from app.services.form import FormService
from app.services.games import DEFAULT_GAMES_LIMIT, MAX_GAMES_LIMIT, GamesService
from app.services.overview import OverviewService

router = APIRouter(prefix="/api/v1/players", tags=["players"])

# Validated by normalize_username so every invalid value gets the same 400 error envelope.
Username = Annotated[str, Path(description="Chess.com username (case-insensitive)")]

_ERRORS: dict[int | str, dict[str, object]] = {
    status: {"model": ErrorResponse} for status in (400, 404, 502, 503, 504)
}


@router.get(
    "/{username}/overview",
    response_model=OverviewResponse,
    responses=_ERRORS,
    summary="30-day Rapid overview",
)
def get_overview(
    username: Username,
    session: Annotated[Session, Depends(get_session)],
    provider: Annotated[GameDataProvider, Depends(get_provider)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    now: Annotated[datetime, Depends(get_now)],
) -> OverviewResponse:
    cache = PlayerDatasetCache(session, provider, settings)
    return OverviewService(session, cache).get_overview(username, now)


Limit = Annotated[int, Query(description=f"Maximum groups returned (1-{MAX_LIMIT}).")]
Sort = Annotated[
    GroupSort,
    Query(description="games: sample size desc; win_rate: desc, nulls last; name: asc."),
]


def _service(session: Session, provider: GameDataProvider, settings: Settings) -> BreakdownService:
    return BreakdownService(session, PlayerDatasetCache(session, provider, settings))


@router.get(
    "/{username}/rating-history",
    response_model=RatingHistoryResponse,
    responses=_ERRORS,
    summary="Rapid rating observations from game records",
)
def get_rating_history(
    username: Username,
    session: Annotated[Session, Depends(get_session)],
    provider: Annotated[GameDataProvider, Depends(get_provider)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    now: Annotated[datetime, Depends(get_now)],
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: Annotated[datetime | None, Query()] = None,
) -> RatingHistoryResponse:
    return _service(session, provider, settings).rating_history(username, now, from_, to)


@router.get(
    "/{username}/openings",
    response_model=OpeningsResponse,
    responses=_ERRORS,
    summary="Opening statistics",
)
def get_openings(
    username: Username,
    session: Annotated[Session, Depends(get_session)],
    provider: Annotated[GameDataProvider, Depends(get_provider)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    now: Annotated[datetime, Depends(get_now)],
    sort: Sort = GroupSort.GAMES,
    limit: Limit = 20,
) -> OpeningsResponse:
    return _service(session, provider, settings).openings(username, now, sort, limit)


@router.get(
    "/{username}/opponents",
    response_model=OpponentsResponse,
    responses=_ERRORS,
    summary="Opponent statistics",
)
def get_opponents(
    username: Username,
    session: Annotated[Session, Depends(get_session)],
    provider: Annotated[GameDataProvider, Depends(get_provider)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    now: Annotated[datetime, Depends(get_now)],
    sort: Sort = GroupSort.GAMES,
    limit: Limit = 20,
) -> OpponentsResponse:
    return _service(session, provider, settings).opponents(username, now, sort, limit)


@router.get(
    "/{username}/games",
    response_model=GameListResponse,
    responses=_ERRORS,
    summary="Eligible games, newest first (cursor pagination)",
)
def list_games(
    username: Username,
    session: Annotated[Session, Depends(get_session)],
    provider: Annotated[GameDataProvider, Depends(get_provider)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    now: Annotated[datetime, Depends(get_now)],
    limit: Annotated[int, Query(description=f"Page size (1-{MAX_GAMES_LIMIT}).")] = (
        DEFAULT_GAMES_LIMIT
    ),
    cursor: Annotated[str | None, Query(description="Opaque value from next_cursor.")] = None,
    result: Annotated[
        PlayerResult | None, Query(description="Filter by the searched player's outcome.")
    ] = None,
) -> GameListResponse:
    service = GamesService(session, PlayerDatasetCache(session, provider, settings))
    return service.list_games(username, now, limit=limit, cursor=cursor, result=result)


@router.get(
    "/{username}/games/{game_id}",
    response_model=GameDetailResponse,
    responses=_ERRORS,
    summary="One eligible game of this player, with parsed PGN when available",
)
def get_game(
    username: Username,
    game_id: Annotated[str, Path(description="Provider game id from the list, e.g. live:123")],
    session: Annotated[Session, Depends(get_session)],
    provider: Annotated[GameDataProvider, Depends(get_provider)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    now: Annotated[datetime, Depends(get_now)],
) -> GameDetailResponse:
    service = GamesService(session, PlayerDatasetCache(session, provider, settings))
    return service.get_game(username, game_id, now)


def _analysis_service(
    session: Session, provider: GameDataProvider, settings: Settings
) -> AnalysisService:
    return AnalysisService(session, PlayerDatasetCache(session, provider, settings), settings)


@router.get(
    "/{username}/games/{game_id}/analysis",
    response_model=AnalysisStateResponse,
    responses=_ERRORS,
    summary="Engine analysis of one game (missing, queued, running, completed or failed)",
)
def get_game_analysis(
    username: Username,
    game_id: Annotated[str, Path(description="Provider game id from the list, e.g. live:123")],
    session: Annotated[Session, Depends(get_session)],
    provider: Annotated[GameDataProvider, Depends(get_provider)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    now: Annotated[datetime, Depends(get_now)],
) -> AnalysisStateResponse:
    return _analysis_service(session, provider, settings).get_state(username, game_id, now)


@router.post(
    "/{username}/games/{game_id}/analysis",
    response_model=AnalysisStateResponse,
    responses=_ERRORS,
    summary="Request engine analysis (idempotent: returns the cached result when present)",
)
def request_game_analysis(
    username: Username,
    game_id: Annotated[str, Path(description="Provider game id from the list, e.g. live:123")],
    session: Annotated[Session, Depends(get_session)],
    provider: Annotated[GameDataProvider, Depends(get_provider)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    now: Annotated[datetime, Depends(get_now)],
) -> AnalysisStateResponse:
    return _analysis_service(session, provider, settings).request(username, game_id, now)


def _form_service(session: Session, provider: GameDataProvider, settings: Settings) -> FormService:
    return FormService(session, PlayerDatasetCache(session, provider, settings), settings)


@router.get(
    "/{username}/form",
    response_model=FormReportResponse,
    responses=_ERRORS,
    summary="Cross-game form report: accuracy trend and where win probability leaks",
)
def get_form(
    username: Username,
    session: Annotated[Session, Depends(get_session)],
    provider: Annotated[GameDataProvider, Depends(get_provider)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    now: Annotated[datetime, Depends(get_now)],
) -> FormReportResponse:
    return _form_service(session, provider, settings).get_form(username, now)


@router.post(
    "/{username}/form/analyze",
    response_model=AnalyzeScopeResponse,
    responses=_ERRORS,
    summary="Queue engine analysis for every game in the current scope that lacks one",
)
def analyze_form(
    username: Username,
    session: Annotated[Session, Depends(get_session)],
    provider: Annotated[GameDataProvider, Depends(get_provider)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    now: Annotated[datetime, Depends(get_now)],
) -> AnalyzeScopeResponse:
    return _form_service(session, provider, settings).analyze_scope(username, now)
