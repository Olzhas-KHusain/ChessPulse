# ADR 0001: Synchronous HTTPX client for the Chess.com provider

Date: 2026-10-20 · Status: accepted

## Context

The backend uses synchronous SQLAlchemy (Issue 1). The Chess.com PubAPI allows
unlimited serial access but may answer parallel requests with `429` and may block
abnormal activity. ChessPulse needs at most a handful of requests per player refresh
(profile, stats, archive list, one or two monthly archives).

## Decision

Use a synchronous `httpx.Client`, one request at a time, with explicit timeouts,
bounded retries and `Retry-After` support. Provider calls run inside synchronous
FastAPI endpoints or services (FastAPI executes them in its worker thread pool).

## Consequences

- Matches the synchronous database layer; no mixed sync/async code paths.
- Serial requests follow the provider's concurrency guidance by construction.
- A refresh blocks one worker thread for its duration; the time budget per request
  (`max_total_seconds`, default 60 s) bounds that.
- Moving to `httpx.AsyncClient` later only affects `app/providers/chess_com/client.py`;
  normalization and domain types are transport-independent.
- Duplicate concurrent refreshes across requests are a cache-layer concern (later issue).
