"""Logging configuration.

Log records are single lines: ``time level logger message key=value ...``. Values
passed through ``extra=`` (player, outcome, error_code, ...) are appended so refresh
outcomes stay searchable. Never pass secrets or raw upstream payloads in ``extra``.
"""

from __future__ import annotations

import logging

# Attributes every LogRecord has; anything else came from ``extra=``.
_STANDARD = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


class KeyValueFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extras = {k: v for k, v in record.__dict__.items() if k not in _STANDARD}
        if not extras:
            return base
        pairs = " ".join(f"{key}={value!r}" for key, value in sorted(extras.items()))
        return f"{base} {pairs}"


def configure_logging(level: str) -> None:
    """Configure the root logger once (idempotent across app factory calls)."""
    root = logging.getLogger()
    root.setLevel(level)
    if any(getattr(h, "_chesspulse", False) for h in root.handlers):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(
        KeyValueFormatter("%(asctime)s %(levelname)s %(name)s %(message)s", "%Y-%m-%dT%H:%M:%S%z")
    )
    handler._chesspulse = True  # type: ignore[attr-defined]
    root.addHandler(handler)
