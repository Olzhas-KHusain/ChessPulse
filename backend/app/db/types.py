"""Custom column types."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import DateTime, Dialect, Enum
from sqlalchemy.types import TypeDecorator


class UtcDateTime(TypeDecorator[datetime]):
    """``TIMESTAMP WITH TIME ZONE`` that only accepts and only returns aware UTC datetimes.

    * Naive datetimes are rejected on write: their meaning depends on the server or
      process time zone, which is exactly the ambiguity the schema must avoid.
    * Aware datetimes in other zones are converted to UTC before they are sent.
    * Values read back are normalized to UTC regardless of the session ``TimeZone``.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("naive datetime is not allowed; pass a timezone-aware UTC datetime")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:  # pragma: no cover - TIMESTAMPTZ always returns aware values
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


def str_enum(enum_cls: type[StrEnum], name: str, length: int = 32) -> Enum:
    """Store a ``StrEnum`` as ``VARCHAR`` guarded by a named ``CHECK`` constraint.

    Native PostgreSQL ENUM types are avoided on purpose: adding a value to a
    VARCHAR + CHECK column is an ordinary, transactional migration, and the
    allowed values remain visible in the migration file.
    """
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=length,
        validate_strings=True,
        values_callable=lambda members: [member.value for member in members],
    )
