"""Shared service-layer exceptions."""

from __future__ import annotations


class InvalidParameterError(ValueError):
    """A query parameter is syntactically valid but violates a documented rule."""

    def __init__(self, parameter: str, message: str) -> None:
        super().__init__(message)
        self.parameter = parameter
        self.message = message
