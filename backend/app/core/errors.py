"""Application-wide error envelope (spec §10) and last-resort handlers.

Every error response has the shape
``{"error": {"code": "...", "message": "...", "request_id": "..."}}``.
Messages are fixed strings; exception text, stack traces, SQL and settings never
reach the client. Unexpected exceptions are logged server-side with the request id.
"""

from __future__ import annotations

import logging
import math
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

_HTTP_CODES: dict[int, tuple[str, str]] = {
    404: ("NOT_FOUND", "The requested resource does not exist."),
    405: ("METHOD_NOT_ALLOWED", "This method is not allowed for the resource."),
}


def request_id(request: Request) -> str:
    """A safe client-supplied ``X-Request-ID`` or a new random id."""
    supplied = request.headers.get("x-request-id", "")
    if 0 < len(supplied) <= 64 and supplied.replace("-", "").isalnum():
        return supplied
    return uuid.uuid4().hex


def error_response(
    request: Request,
    status: int,
    code: str,
    message: str,
    retry_after: float | None = None,
) -> JSONResponse:
    rid = request_id(request)
    headers = {"X-Request-ID": rid}
    if retry_after is not None:
        headers["Retry-After"] = str(max(1, math.ceil(retry_after)))
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "request_id": rid}},
        headers=headers,
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, StarletteHTTPException)
        code, message = _HTTP_CODES.get(exc.status_code, ("HTTP_ERROR", "The request failed."))
        return error_response(request, exc.status_code, code, message)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        response = error_response(
            request, 500, "INTERNAL_ERROR", "An unexpected error occurred. Please try again."
        )
        logger.error(
            "unhandled exception",
            exc_info=exc,
            extra={"request_id": response.headers["X-Request-ID"], "path": request.url.path},
        )
        return response
