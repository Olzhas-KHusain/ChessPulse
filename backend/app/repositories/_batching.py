"""Helpers for bounded batch statements."""

from __future__ import annotations

from collections.abc import Iterator, Sequence

# Keeps every multi-row statement well below PostgreSQL's 65,535 bind-parameter limit
# (the widest row, a game, binds 15 values).
BATCH_SIZE = 500


def chunked[T](items: Sequence[T], size: int = BATCH_SIZE) -> Iterator[Sequence[T]]:
    """Yield consecutive slices of at most ``size`` items."""
    if size <= 0:
        raise ValueError("size must be positive")
    for start in range(0, len(items), size):
        yield items[start : start + size]


def require_lowercase(value: str, field: str) -> None:
    """Reject values that violate the stored lowercase invariant.

    Normalization belongs to the service layer; repositories only refuse
    unnormalized input so that a bug fails here instead of creating a duplicate.
    """
    if not value or value != value.lower():
        raise ValueError(f"{field} must be a non-empty, normalized (lowercase) value")
