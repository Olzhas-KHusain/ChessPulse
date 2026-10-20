"""HTTP transport for the Chess.com Published-Data API (PubAPI).

Responsibilities: explicit timeouts, bounded retries with backoff, ``Retry-After``,
status-code mapping to :class:`ProviderErrorCode`, response-size limits, safe
redirect handling, and JSON decoding. It knows nothing about the meaning of the
payload; see ``normalize.py`` for that.

Verified behavior (https://www.chess.com/news/view/published-data-api):

* 200 success; 301 the correct location is known; 304 not modified (conditional
  requests, not used yet); 404 malformed URL or data not available; 410 data will
  never be available; 429 rate limited. No other codes are documented.
* Serial access is unlimited; parallel requests may receive 429. This client is
  synchronous and issues one request at a time.
* A recognizable User-Agent with contact information is recommended.
"""

from __future__ import annotations

import json
import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from enum import StrEnum
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.providers.errors import ProviderError, ProviderErrorCode
from app.providers.types import ResponseMeta

logger = logging.getLogger(__name__)

API_HOST = "api.chess.com"
BASE_URL = f"https://{API_HOST}/pub"

# Monthly archives of very active players can be a few megabytes; anything far larger
# is treated as invalid rather than buffered without limit (decompressed size).
DEFAULT_MAX_RESPONSE_BYTES = 25 * 1024 * 1024
MAX_REDIRECTS = 3

_RETRYABLE_STATUS = {500, 502, 503, 504}
_REDIRECT_STATUS = {301, 302, 307, 308}


class ResourceKind(StrEnum):
    """Which documented resource a request targets (drives 404 interpretation)."""

    PROFILE = "profile"
    STATS = "stats"
    ARCHIVES = "archives"
    MONTH_ARCHIVE = "month_archive"


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Bounded retry configuration.

    ``max_retries`` extra attempts are made only for transient failures: timeouts,
    connection errors, 429, and 500/502/503/504. A delay longer than
    ``max_delay_seconds`` (including a provider ``Retry-After``) is never waited;
    the error is raised immediately with ``retry_after`` so the caller can decide.
    ``max_total_seconds`` bounds the whole call including waits.
    """

    max_retries: int = 2
    backoff_base_seconds: float = 0.5
    max_delay_seconds: float = 10.0
    max_total_seconds: float = 60.0

    def __post_init__(self) -> None:
        if self.max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        if self.backoff_base_seconds < 0 or self.max_delay_seconds < 0:
            raise ValueError("delays must be >= 0")
        if self.max_total_seconds <= 0:
            raise ValueError("max_total_seconds must be positive")


@dataclass(frozen=True, slots=True)
class JsonResponse:
    payload: dict[str, Any]
    meta: ResponseMeta


class _Retryable(Exception):
    """Internal: a failed attempt that the retry policy may repeat."""

    def __init__(self, error: ProviderError) -> None:
        super().__init__(str(error))
        self.error = error


def parse_retry_after(value: str | None, now: datetime) -> float | None:
    """Parse ``Retry-After`` (delta-seconds or HTTP-date) into seconds from ``now``."""
    if value is None:
        return None
    value = value.strip()
    if value.isdigit():
        return float(int(value))
    try:
        moment = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return max(0.0, (moment - now).total_seconds())


def parse_max_age(cache_control: str | None) -> int | None:
    if not cache_control:
        return None
    for directive in cache_control.split(","):
        name, _, raw = directive.strip().partition("=")
        if name.lower() == "max-age" and raw.strip().isdigit():
            return int(raw.strip())
    return None


def _short_header(value: str | None, limit: int = 256) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value if 0 < len(value) <= limit else None


class ChessComHttpClient:
    """Synchronous, retrying JSON client for ``https://api.chess.com/pub``.

    All collaborators that make behavior time-dependent (sleep, clocks, jitter) and
    the HTTP transport are injectable, so tests never touch the network or wait.
    """

    def __init__(
        self,
        *,
        user_agent: str,
        timeout_seconds: float = 10.0,
        retry: RetryPolicy | None = None,
        transport: httpx.BaseTransport | None = None,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        jitter: Callable[[], float] = random.random,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._retry = retry or RetryPolicy()
        self._max_response_bytes = max_response_bytes
        self._sleep = sleep
        self._monotonic = monotonic
        self._now = now
        self._jitter = jitter
        self._client = httpx.Client(
            base_url=BASE_URL,
            headers={
                "User-Agent": user_agent,
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
            },
            timeout=httpx.Timeout(timeout_seconds),
            transport=transport,
            follow_redirects=False,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> ChessComHttpClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # -- public ---------------------------------------------------------------

    def get_json(self, path: str, resource: ResourceKind) -> JsonResponse:
        """GET ``BASE_URL + path`` and return a JSON object, applying the retry policy.

        Raises:
            ProviderError: for every failure, after retries where applicable.
        """
        started = self._monotonic()
        attempts = self._retry.max_retries + 1
        for attempt in range(1, attempts + 1):
            try:
                return self._attempt(path, resource, attempt)
            except ProviderError as permanent:
                permanent.attempts = attempt
                raise
            except _Retryable as retryable:
                error = retryable.error
                error.attempts = attempt
                if attempt == attempts:
                    raise error from None
                delay = self._delay(attempt, error.retry_after)
                elapsed = self._monotonic() - started
                if delay > self._retry.max_delay_seconds or (
                    elapsed + delay > self._retry.max_total_seconds
                ):
                    raise error from None
                logger.warning(
                    "chess_com request failed; retrying",
                    extra={
                        "resource": resource.value,
                        "error_code": error.code.value,
                        "status_code": error.status_code,
                        "attempt": attempt,
                        "delay_seconds": round(delay, 3),
                    },
                )
                self._sleep(delay)
        raise AssertionError("unreachable")  # pragma: no cover

    # -- internals ------------------------------------------------------------

    def _delay(self, attempt: int, retry_after: float | None) -> float:
        if retry_after is not None:
            return retry_after
        backoff = self._retry.backoff_base_seconds * float(1 << (attempt - 1))
        # Jitter in [50%, 100%] of the exponential backoff.
        return backoff * (0.5 + 0.5 * self._jitter())

    def _attempt(self, path: str, resource: ResourceKind, attempt: int) -> JsonResponse:
        url: str = path
        for _ in range(MAX_REDIRECTS + 1):
            status, headers, body = self._send(url, attempt)
            if status in _REDIRECT_STATUS:
                url = self._redirect_target(headers.get("location"))
                continue
            return self._handle(status, headers, body, resource)
        raise ProviderError(
            ProviderErrorCode.UPSTREAM_INVALID_RESPONSE,
            "Too many redirects from the provider.",
        )

    def _send(self, url: str, attempt: int) -> tuple[int, httpx.Headers, bytes]:
        try:
            with self._client.stream("GET", url) as response:
                declared = response.headers.get("content-length")
                if declared and declared.isdigit() and int(declared) > self._max_response_bytes:
                    raise self._too_large(response.status_code)
                chunks: list[bytes] = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > self._max_response_bytes:
                        raise self._too_large(response.status_code)
                    chunks.append(chunk)
                return response.status_code, response.headers, b"".join(chunks)
        except httpx.TimeoutException:
            raise _Retryable(
                ProviderError(
                    ProviderErrorCode.UPSTREAM_TIMEOUT,
                    "The provider did not respond in time.",
                    attempts=attempt,
                )
            ) from None
        except httpx.DecodingError:
            raise ProviderError(
                ProviderErrorCode.UPSTREAM_INVALID_RESPONSE,
                "The provider response could not be decoded.",
                attempts=attempt,
            ) from None
        except httpx.TransportError:
            raise _Retryable(
                ProviderError(
                    ProviderErrorCode.UPSTREAM_UNAVAILABLE,
                    "The provider could not be reached.",
                    attempts=attempt,
                )
            ) from None

    def _too_large(self, status: int) -> ProviderError:
        return ProviderError(
            ProviderErrorCode.UPSTREAM_INVALID_RESPONSE,
            "The provider response exceeded the size limit.",
            status_code=status,
        )

    def _redirect_target(self, location: str | None) -> str:
        """Follow only redirects that stay on https://api.chess.com/pub/."""
        if location:
            parts = urlsplit(location)
            if not parts.scheme and not parts.netloc and location.startswith("/pub/"):
                return f"https://{API_HOST}{location}"
            if (
                parts.scheme == "https"
                and parts.hostname == API_HOST
                and (parts.path.startswith("/pub/"))
            ):
                return location
        raise ProviderError(
            ProviderErrorCode.UPSTREAM_INVALID_RESPONSE,
            "The provider redirected to an unsupported location.",
        )

    def _handle(
        self, status: int, headers: httpx.Headers, body: bytes, resource: ResourceKind
    ) -> JsonResponse:
        if status == 200:
            return JsonResponse(payload=self._decode(body, status), meta=self._meta(headers))

        retry_after = parse_retry_after(headers.get("retry-after"), self._now())
        if status in (404, 410):
            code = (
                ProviderErrorCode.PLAYER_NOT_FOUND
                if resource is ResourceKind.PROFILE
                else ProviderErrorCode.UPSTREAM_NOT_FOUND
            )
            raise ProviderError(
                code, "The provider reported that the data does not exist.", status_code=status
            )
        if status in (401, 403):
            raise ProviderError(
                ProviderErrorCode.UPSTREAM_FORBIDDEN,
                "The provider refused the request.",
                status_code=status,
            )
        if status == 429:
            raise _Retryable(
                ProviderError(
                    ProviderErrorCode.UPSTREAM_RATE_LIMITED,
                    "The provider rate-limited the request.",
                    status_code=status,
                    retry_after=retry_after,
                )
            )
        if status in _RETRYABLE_STATUS:
            raise _Retryable(
                ProviderError(
                    ProviderErrorCode.UPSTREAM_UNAVAILABLE,
                    "The provider is temporarily unavailable.",
                    status_code=status,
                    retry_after=retry_after,
                )
            )
        if 300 <= status < 400:
            # 304 is only valid for conditional requests, which this client does not send.
            raise ProviderError(
                ProviderErrorCode.UPSTREAM_INVALID_RESPONSE,
                "The provider returned an unexpected redirect or cache status.",
                status_code=status,
            )
        raise ProviderError(
            ProviderErrorCode.UPSTREAM_UNKNOWN_ERROR,
            "The provider returned an unexpected status.",
            status_code=status,
        )

    @staticmethod
    def _decode(body: bytes, status: int) -> dict[str, Any]:
        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
            raise ProviderError(
                ProviderErrorCode.UPSTREAM_INVALID_RESPONSE,
                "The provider returned invalid JSON.",
                status_code=status,
            ) from None
        if not isinstance(payload, dict):
            raise ProviderError(
                ProviderErrorCode.UPSTREAM_INVALID_RESPONSE,
                "The provider returned JSON that is not an object.",
                status_code=status,
            )
        return payload

    def _meta(self, headers: httpx.Headers) -> ResponseMeta:
        return ResponseMeta(
            fetched_at=self._now(),
            etag=_short_header(headers.get("etag")),
            last_modified=_short_header(headers.get("last-modified")),
            max_age_seconds=parse_max_age(headers.get("cache-control")),
        )
