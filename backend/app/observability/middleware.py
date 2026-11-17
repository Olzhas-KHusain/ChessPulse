"""HTTP metrics middleware.

The route label is the matched FastAPI route (``/api/v1/players/{username}/overview``),
not the raw URL, so usernames and arbitrary ids do not create unbounded label
cardinality. Unmatched requests are grouped under ``unmatched``.
"""

from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.observability.metrics import record_http_request

_EXCLUDED_PATHS = {"/health", "/metrics"}


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in _EXCLUDED_PATHS:
            return await call_next(request)

        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            route = getattr(request.scope.get("route"), "path", None) or "unmatched"
            record_http_request(
                method=request.method,
                route=route,
                status_code=status_code,
                duration_seconds=time.perf_counter() - started,
            )
