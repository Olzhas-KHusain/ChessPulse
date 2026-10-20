"""Domain-error → HTTP mapping with the spec §10 error envelope.

Messages are fixed, safe strings; internal exception text never reaches clients.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.cache.policy import DatasetUnavailableError
from app.cache.service import REFRESH_IN_PROGRESS
from app.core.errors import error_response
from app.providers.chess_com import InvalidUsernameError
from app.providers.errors import ProviderError, ProviderErrorCode
from app.services.breakdowns import InvalidParameterError
from app.services.games import GameNotFoundError

# (status, message) for upstream failures when no usable cached data exists.
_UNAVAILABLE: dict[str, tuple[int, str]] = {
    ProviderErrorCode.UPSTREAM_TIMEOUT.value: (504, "Chess.com did not respond in time."),
    ProviderErrorCode.UPSTREAM_INVALID_RESPONSE.value: (
        502,
        "Chess.com returned data that could not be used.",
    ),
    ProviderErrorCode.UPSTREAM_RATE_LIMITED.value: (
        503,
        "Chess.com is limiting requests. Please try again later.",
    ),
    REFRESH_IN_PROGRESS: (503, "This player's data is being loaded. Please retry shortly."),
}
_DEFAULT_UNAVAILABLE = (503, "Game data is temporarily unavailable.")


def register_api_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(InvalidUsernameError)
    async def _invalid_username(request: Request, _: Exception) -> JSONResponse:
        return error_response(
            request,
            400,
            "INVALID_USERNAME",
            "Usernames contain 1-64 letters, digits, underscores or hyphens.",
        )

    @app.exception_handler(ProviderError)
    async def _provider(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, ProviderError)
        if exc.code is ProviderErrorCode.PLAYER_NOT_FOUND:
            return error_response(
                request, 404, exc.code.value, "No Chess.com player with this username."
            )
        status, message = _UNAVAILABLE.get(exc.code.value, _DEFAULT_UNAVAILABLE)
        return error_response(request, status, exc.code.value, message, exc.retry_after)

    @app.exception_handler(DatasetUnavailableError)
    async def _unavailable(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, DatasetUnavailableError)
        status, message = _UNAVAILABLE.get(exc.code, _DEFAULT_UNAVAILABLE)
        return error_response(request, status, exc.code, message, exc.retry_after_seconds)

    @app.exception_handler(GameNotFoundError)
    async def _game_not_found(request: Request, _: Exception) -> JSONResponse:
        return error_response(
            request, 404, "GAME_NOT_FOUND", "This game is not in the player's 30-day Rapid games."
        )

    @app.exception_handler(InvalidParameterError)
    async def _invalid_parameter(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, InvalidParameterError)
        return error_response(request, 400, "INVALID_PARAMETER", exc.message)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, RequestValidationError)
        # Name the offending parameters only; never echo the submitted values.
        names = sorted({str(err["loc"][-1]) for err in exc.errors() if err.get("loc")})
        return error_response(
            request, 400, "INVALID_PARAMETER", f"Invalid value for: {', '.join(names)}."
        )
