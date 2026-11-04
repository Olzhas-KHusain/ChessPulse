"""Free-board endpoints: evaluate a position and classify one played move."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.v1.dependencies import get_board_service
from app.schemas.board import (
    BoardEngineOut,
    BoardEvaluateRequest,
    BoardEvaluateResponse,
    BoardMoveRequest,
    BoardMoveResponse,
)
from app.schemas.overview import ErrorResponse
from app.services.board import BoardAnalysisService

router = APIRouter(prefix="/api/v1/board", tags=["board"])

_ERRORS: dict[int | str, dict[str, object]] = {
    status: {"model": ErrorResponse} for status in (400, 502, 503, 504)
}


def _engine(service: BoardAnalysisService) -> BoardEngineOut:
    identity = service.engine_identity
    return BoardEngineOut(name=identity.name, version=identity.version, depth=service.depth)


@router.post(
    "/evaluate",
    response_model=BoardEvaluateResponse,
    responses=_ERRORS,
    summary="Evaluate an arbitrary chess position",
)
def evaluate(
    payload: BoardEvaluateRequest,
    service: Annotated[BoardAnalysisService, Depends(get_board_service)],
) -> BoardEvaluateResponse:
    result = service.evaluate(payload.fen)
    return BoardEvaluateResponse(
        fen=result.fen,
        turn=result.turn,
        status=result.status,
        eval_cp=result.eval_cp,
        mate=result.mate,
        best_move_uci=result.best_move_uci,
        best_move_san=result.best_move_san,
        engine=_engine(service),
    )


@router.post(
    "/move",
    response_model=BoardMoveResponse,
    responses=_ERRORS,
    summary="Play one legal move and classify it",
)
def move(
    payload: BoardMoveRequest,
    service: Annotated[BoardAnalysisService, Depends(get_board_service)],
) -> BoardMoveResponse:
    result = service.analyze_move(payload.fen, payload.move_uci)
    return BoardMoveResponse(
        fen_before=result.fen_before,
        fen_after=result.fen_after,
        turn=result.turn,
        move_number=result.move_number,
        san=result.san,
        uci=result.uci,
        eval_before_cp=result.eval_before_cp,
        eval_after_cp=result.eval_after_cp,
        mate_after=result.mate_after,
        cp_loss=result.cp_loss,
        classification=result.classification,
        best_move_uci=result.best_move_uci,
        best_move_san=result.best_move_san,
        best_move_after_uci=result.best_move_after_uci,
        best_move_after_san=result.best_move_after_san,
        status_after=result.status_after,
        engine=_engine(service),
    )
