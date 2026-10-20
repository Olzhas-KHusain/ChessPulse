"""Helpers for provider tests. No test in this package touches the network."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.providers.chess_com import ChessComHttpClient, ChessComProvider, RetryPolicy

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 10, 20, 7, 0, tzinfo=UTC)

Handler = Callable[[httpx.Request], httpx.Response]


def load_fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def json_response(status: int, payload: Any, **headers: str) -> httpx.Response:
    return httpx.Response(status, json=payload, headers=headers)


@dataclass
class Harness:
    """A provider wired to a mock transport, a fake clock and a recorded sleep."""

    handler: Handler
    retry: RetryPolicy = field(default_factory=lambda: RetryPolicy(max_retries=2))
    max_response_bytes: int = 1024 * 1024
    requests: list[httpx.Request] = field(default_factory=list)
    sleeps: list[float] = field(default_factory=list)
    clock: float = 0.0

    def _sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.clock += seconds

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.handler(request)

    def client(self) -> ChessComHttpClient:
        return ChessComHttpClient(
            user_agent="ChessPulse-tests/1.0 (contact: tests@example.invalid)",
            timeout_seconds=5,
            retry=self.retry,
            transport=httpx.MockTransport(self._handle),
            max_response_bytes=self.max_response_bytes,
            sleep=self._sleep,
            monotonic=lambda: self.clock,
            now=lambda: NOW,
            jitter=lambda: 1.0,
        )

    def provider(self) -> ChessComProvider:
        return ChessComProvider(self.client())


def routes(table: dict[str, Handler | httpx.Response]) -> Handler:
    """Dispatch by request path; unknown paths fail the test loudly."""

    def handler(request: httpx.Request) -> httpx.Response:
        target = table.get(request.url.path)
        if target is None:
            raise AssertionError(f"unexpected request: {request.url}")
        return target(request) if callable(target) else target

    return handler


def sequence(*responses: httpx.Response | Exception) -> Handler:
    """Return the given responses (or raise the exceptions) in order."""
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        if not queue:
            raise AssertionError("more requests than expected")
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    return handler


@pytest.fixture
def harness_factory() -> Callable[..., Harness]:
    return Harness
