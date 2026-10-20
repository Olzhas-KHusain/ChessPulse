"""Transport behavior: status mapping, timeouts, retries, Retry-After, limits, redirects."""

from __future__ import annotations

import httpx
import pytest

from app.providers.chess_com import RetryPolicy
from app.providers.chess_com.client import parse_max_age, parse_retry_after
from app.providers.errors import ProviderError, ProviderErrorCode
from tests.providers.conftest import NOW, Harness, json_response, load_fixture, sequence

PROFILE = load_fixture("profile_full.json")
OK = json_response(200, PROFILE)


def _error(harness: Harness) -> ProviderError:
    with pytest.raises(ProviderError) as excinfo:
        harness.provider().get_profile("example_player")
    return excinfo.value


# --- success and request shape --------------------------------------------------------


def test_successful_lookup_sends_documented_request() -> None:
    harness = Harness(sequence(OK))
    profile = harness.provider().get_profile("Example_Player")

    assert profile.username == "example_player"
    (request,) = harness.requests
    assert str(request.url) == "https://api.chess.com/pub/player/example_player"
    assert request.headers["user-agent"].startswith("ChessPulse-tests/1.0")
    assert request.headers["accept"] == "application/json"
    assert "gzip" in request.headers["accept-encoding"]
    assert harness.sleeps == []


def test_response_metadata_is_captured() -> None:
    response = httpx.Response(
        200,
        json=PROFILE,
        headers={
            "ETag": '"abc123"',
            "Last-Modified": "Mon, 19 Oct 2026 10:00:00 GMT",
            "Cache-Control": "public, max-age=43200",
        },
    )
    profile = Harness(sequence(response)).provider().get_profile("example_player")
    assert profile.meta.fetched_at == NOW
    assert profile.meta.etag == '"abc123"'
    assert profile.meta.last_modified == "Mon, 19 Oct 2026 10:00:00 GMT"
    assert profile.meta.max_age_seconds == 43200


# --- confirmed not found vs outages ----------------------------------------------------


@pytest.mark.parametrize("status", [404, 410])
def test_missing_profile_is_a_confirmed_not_found_without_retry(status: int) -> None:
    harness = Harness(sequence(json_response(status, load_fixture("not_found.json"))))
    error = _error(harness)
    assert error.code is ProviderErrorCode.PLAYER_NOT_FOUND
    assert error.is_confirmed_missing_player
    assert error.status_code == status
    assert len(harness.requests) == 1


def test_missing_sub_resource_is_not_reported_as_missing_player() -> None:
    harness = Harness(sequence(json_response(404, load_fixture("not_found.json"))))
    with pytest.raises(ProviderError) as excinfo:
        harness.provider().get_stats("example_player")
    assert excinfo.value.code is ProviderErrorCode.UPSTREAM_NOT_FOUND
    assert not excinfo.value.is_confirmed_missing_player


def test_timeout_is_retried_then_reported() -> None:
    timeout = httpx.ReadTimeout("slow")
    harness = Harness(sequence(timeout, timeout, timeout))
    error = _error(harness)
    assert error.code is ProviderErrorCode.UPSTREAM_TIMEOUT
    assert not error.is_confirmed_missing_player
    assert error.attempts == 3
    assert len(harness.requests) == 3
    assert harness.sleeps == [0.5, 1.0]  # exponential backoff (jitter fixed at 100%)


def test_connection_error_maps_to_unavailable() -> None:
    harness = Harness(sequence(*[httpx.ConnectError("refused")] * 3))
    assert _error(harness).code is ProviderErrorCode.UPSTREAM_UNAVAILABLE


def test_transient_server_error_recovers() -> None:
    harness = Harness(sequence(json_response(503, {}), OK))
    assert harness.provider().get_profile("example_player").username == "example_player"
    assert len(harness.requests) == 2


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_persistent_server_error_is_unavailable(status: int) -> None:
    harness = Harness(sequence(*[json_response(status, {})] * 3))
    error = _error(harness)
    assert error.code is ProviderErrorCode.UPSTREAM_UNAVAILABLE
    assert error.status_code == status
    assert len(harness.requests) == 3


def test_retries_are_bounded_by_policy() -> None:
    harness = Harness(sequence(json_response(503, {})), retry=RetryPolicy(max_retries=0))
    assert _error(harness).attempts == 1
    assert harness.sleeps == []


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (403, ProviderErrorCode.UPSTREAM_FORBIDDEN),
        (401, ProviderErrorCode.UPSTREAM_FORBIDDEN),
        (400, ProviderErrorCode.UPSTREAM_UNKNOWN_ERROR),
        (418, ProviderErrorCode.UPSTREAM_UNKNOWN_ERROR),
        (304, ProviderErrorCode.UPSTREAM_INVALID_RESPONSE),
    ],
)
def test_permanent_errors_are_not_retried(status: int, code: ProviderErrorCode) -> None:
    harness = Harness(sequence(httpx.Response(status)))
    assert _error(harness).code is code
    assert len(harness.requests) == 1


# --- rate limiting ----------------------------------------------------------------


def test_rate_limit_respects_retry_after_seconds() -> None:
    harness = Harness(sequence(json_response(429, {}, **{"Retry-After": "3"}), OK))
    harness.provider().get_profile("example_player")
    assert harness.sleeps == [3.0]


def test_rate_limit_respects_retry_after_http_date() -> None:
    header = "Tue, 20 Oct 2026 07:00:04 GMT"  # NOW + 4 s
    harness = Harness(sequence(json_response(429, {}, **{"Retry-After": header}), OK))
    harness.provider().get_profile("example_player")
    assert harness.sleeps == [4.0]


def test_rate_limit_with_excessive_retry_after_fails_fast() -> None:
    harness = Harness(
        sequence(json_response(429, {}, **{"Retry-After": "120"})),
        retry=RetryPolicy(max_retries=2, max_delay_seconds=10),
    )
    error = _error(harness)
    assert error.code is ProviderErrorCode.UPSTREAM_RATE_LIMITED
    assert error.retry_after == 120.0
    assert harness.sleeps == []
    assert len(harness.requests) == 1


def test_persistent_rate_limit_is_reported_after_bounded_retries() -> None:
    harness = Harness(sequence(*[json_response(429, {})] * 3))
    error = _error(harness)
    assert error.code is ProviderErrorCode.UPSTREAM_RATE_LIMITED
    assert error.retry_after is None
    assert len(harness.requests) == 3


def test_total_time_budget_stops_retries() -> None:
    harness = Harness(
        sequence(*[json_response(429, {}, **{"Retry-After": "8"})] * 3),
        retry=RetryPolicy(max_retries=5, max_delay_seconds=10, max_total_seconds=12),
    )
    assert _error(harness).code is ProviderErrorCode.UPSTREAM_RATE_LIMITED
    assert harness.sleeps == [8.0]
    assert len(harness.requests) == 2


# --- malformed responses ---------------------------------------------------------


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"<html>not json</html>"),
        httpx.Response(200, content=b"\xff\xfe"),
        httpx.Response(200, json=[1, 2, 3]),
        httpx.Response(200, json={"player_id": 1}),  # profile without username
    ],
)
def test_malformed_success_is_invalid_and_not_retried(response: httpx.Response) -> None:
    harness = Harness(sequence(response))
    assert _error(harness).code is ProviderErrorCode.UPSTREAM_INVALID_RESPONSE
    assert len(harness.requests) == 1


def test_oversized_response_is_rejected() -> None:
    harness = Harness(sequence(httpx.Response(200, content=b"{" + b" " * 2048 + b"}")))
    harness.max_response_bytes = 1024
    assert _error(harness).code is ProviderErrorCode.UPSTREAM_INVALID_RESPONSE


# --- redirects -------------------------------------------------------------------


def test_redirect_within_the_api_is_followed() -> None:
    target = "https://api.chess.com/pub/player/new_name"
    harness = Harness(sequence(httpx.Response(301, headers={"Location": target}), OK))
    harness.provider().get_profile("old_name")
    assert [str(r.url) for r in harness.requests] == [
        "https://api.chess.com/pub/player/old_name",
        target,
    ]


@pytest.mark.parametrize(
    "location",
    ["https://evil.example/pub/player/x", "http://api.chess.com/pub/player/x", "/other/path", ""],
)
def test_redirect_outside_the_api_is_rejected(location: str) -> None:
    harness = Harness(sequence(httpx.Response(301, headers={"Location": location})))
    assert _error(harness).code is ProviderErrorCode.UPSTREAM_INVALID_RESPONSE
    assert len(harness.requests) == 1


def test_redirect_loop_is_bounded() -> None:
    loop = httpx.Response(301, headers={"Location": "/pub/player/example_player"})
    harness = Harness(sequence(*[loop] * 4))
    assert _error(harness).code is ProviderErrorCode.UPSTREAM_INVALID_RESPONSE


# --- header parsing ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("5", 5.0),
        (" 0 ", 0.0),
        ("Tue, 20 Oct 2026 07:00:10 GMT", 10.0),
        ("Tue, 20 Oct 2026 06:00:00 GMT", 0.0),  # in the past
        ("soon", None),
        ("-3", None),
    ],
)
def test_parse_retry_after(value: str | None, expected: float | None) -> None:
    assert parse_retry_after(value, NOW) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, None), ("max-age=60", 60), ("public, MAX-AGE=10", 10), ("no-cache", None)],
)
def test_parse_max_age(value: str | None, expected: int | None) -> None:
    assert parse_max_age(value) == expected


def test_retry_policy_validation() -> None:
    with pytest.raises(ValueError):
        RetryPolicy(max_retries=-1)
    with pytest.raises(ValueError):
        RetryPolicy(max_total_seconds=0)


def test_gzip_response_is_decoded_and_limit_applies_to_decompressed_size() -> None:
    import gzip
    import json

    body = gzip.compress(json.dumps(PROFILE).encode())
    ok = httpx.Response(200, content=body, headers={"Content-Encoding": "gzip"})
    assert Harness(sequence(ok)).provider().get_profile("example_player").username == (
        "example_player"
    )

    bomb = gzip.compress(b"{" + b" " * 100_000 + b"}")
    assert len(bomb) < 1024
    harness = Harness(
        sequence(httpx.Response(200, content=bomb, headers={"Content-Encoding": "gzip"}))
    )
    harness.max_response_bytes = 10_000
    assert _error(harness).code is ProviderErrorCode.UPSTREAM_INVALID_RESPONSE


def test_permanent_error_after_a_retry_reports_all_attempts() -> None:
    harness = Harness(sequence(json_response(503, {}), json_response(404, {})))
    error = _error(harness)
    assert error.code is ProviderErrorCode.PLAYER_NOT_FOUND
    assert error.attempts == 2
