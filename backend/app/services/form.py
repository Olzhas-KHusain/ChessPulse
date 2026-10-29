"""Cross-game form report: load analyses, aggregate, and queue missing games."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, cast

from sqlalchemy.orm import Session

from app.analytics.form import (
    AccuracyPoint,
    AnalysedGame,
    GroupStats,
    Moment,
    build_form_report,
)
from app.analytics.window import analysis_window
from app.cache.service import PlayerDatasetCache
from app.core.config import Settings
from app.models import Player, TimeClass
from app.repositories import AnalysisRepository
from app.schemas.form import (
    AnalyzeScopeResponse,
    FormAccuracyPoint,
    FormGroup,
    FormLeak,
    FormMoment,
    FormReportResponse,
)
from app.schemas.overview import Period
from app.services.analysis import analysis_profile

Color = Literal["white", "black"]
Classification = Literal["best", "good", "inaccuracy", "mistake", "blunder"]
Phase = Literal["opening", "middlegame", "late"]
LeakKind = Literal["phase", "color", "opening"]


class FormService:
    def __init__(self, session: Session, cache: PlayerDatasetCache, settings: Settings) -> None:
        self._session = session
        self._cache = cache
        self._settings = settings
        self._analysis = AnalysisRepository(session)

    def get_form(
        self, username: str, now: datetime, *, time_class: TimeClass = TimeClass.RAPID
    ) -> FormReportResponse:
        status = self._cache.ensure_dataset(username, now)
        player = self._session.get_one(Player, status.player_id)
        window = analysis_window(now)
        profile = analysis_profile(self._settings)

        rows = self._analysis.list_analysed_games(
            status.player_id,
            profile_hash=profile,
            start=window.start,
            end=window.end,
            time_class=time_class,
        )
        total = len(
            self._analysis.list_scope_game_ids(
                status.player_id, start=window.start, end=window.end, time_class=time_class
            )
        )
        counts = self._analysis.job_counts(
            status.player_id,
            profile_hash=profile,
            start=window.start,
            end=window.end,
            time_class=time_class,
        )
        report = build_form_report(
            [
                AnalysedGame(
                    game_id=row.provider_game_id,
                    played_at=row.played_at,
                    color=row.color.value,
                    result=row.result.value,
                    opponent=row.opponent,
                    opening_key=row.opening_key,
                    opening_name=row.opening_name,
                    game_url=row.game_url,
                    payload=row.payload,
                )
                for row in rows
            ]
        )

        leak = report.primary_leak
        return FormReportResponse(
            username=player.username,
            period=Period(start=window.start, end=window.end),
            time_class=time_class.value,
            data_status=status.data_status.value,
            refresh_error=status.refresh_error,
            as_of=now,
            last_successful_update=status.last_successful_update,
            games_total=total,
            games_analyzed=report.games_analyzed,
            games_queued=counts.get("queued", 0),
            games_running=counts.get("running", 0),
            games_failed=counts.get("failed", 0),
            accuracy_mean=report.accuracy_mean,
            opponent_accuracy_mean=report.opponent_accuracy_mean,
            acpl_mean=report.acpl_mean,
            wp_loss_per_game=report.wp_loss_per_game,
            accuracy_trend=[_point(p) for p in report.accuracy_trend],
            by_phase=[_group(g) for g in report.by_phase],
            by_color=[_group(g) for g in report.by_color],
            by_opening=[_group(g) for g in report.by_opening],
            top_moments=[_moment(m) for m in report.top_moments],
            primary_leak=(
                FormLeak(
                    kind=cast(LeakKind, leak.kind),
                    label=leak.label,
                    wp_loss_per_game=leak.wp_loss_per_game,
                    games=leak.games,
                    moves=leak.moves,
                    blunders=leak.blunders,
                    mistakes=leak.mistakes,
                )
                if leak is not None
                else None
            ),
        )

    def analyze_scope(
        self, username: str, now: datetime, *, time_class: TimeClass = TimeClass.RAPID
    ) -> AnalyzeScopeResponse:
        """Queue every game in the scope that has no stored analysis yet."""
        status = self._cache.ensure_dataset(username, now)
        player = self._session.get_one(Player, status.player_id)
        window = analysis_window(now)
        profile = analysis_profile(self._settings)

        game_ids = self._analysis.list_scope_game_ids(
            status.player_id, start=window.start, end=window.end, time_class=time_class
        )
        analysed = self._analysis.analysed_game_ids(game_ids, profile)
        missing = [game_id for game_id in game_ids if game_id not in analysed]
        queued = self._analysis.enqueue(missing, profile)
        self._session.commit()

        counts = self._analysis.job_counts(
            status.player_id,
            profile_hash=profile,
            start=window.start,
            end=window.end,
            time_class=time_class,
        )
        return AnalyzeScopeResponse(
            username=player.username,
            time_class=time_class.value,
            games_total=len(game_ids),
            already_analyzed=len(analysed),
            queued=queued,
            pending=counts.get("queued", 0) + counts.get("running", 0),
        )


def _group(group: GroupStats) -> FormGroup:
    return FormGroup(
        key=group.key,
        label=group.label,
        games=group.games,
        moves=group.moves,
        blunders=group.blunders,
        mistakes=group.mistakes,
        inaccuracies=group.inaccuracies,
        acpl=group.acpl,
        accuracy=group.accuracy,
        wp_loss_per_game=group.wp_loss_per_game,
    )


def _point(point: AccuracyPoint) -> FormAccuracyPoint:
    return FormAccuracyPoint(
        game_id=point.game_id,
        played_at=point.played_at,
        color=cast(Color, point.color),
        result=point.result,
        opponent=point.opponent,
        accuracy=point.accuracy,
        acpl=point.acpl,
        blunders=point.blunders,
        mistakes=point.mistakes,
    )


def _moment(moment: Moment) -> FormMoment:
    return FormMoment(
        game_id=moment.game_id,
        played_at=moment.played_at,
        color=cast(Color, moment.color),
        opponent=moment.opponent,
        move_number=moment.move_number,
        san=moment.san,
        classification=cast(Classification, moment.classification),
        cp_loss=moment.cp_loss,
        wp_loss=moment.wp_loss,
        phase=cast(Phase, moment.phase),
        opening_name=moment.opening_name,
        game_url=moment.game_url,
    )
