"""Normalized opening identifiers."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import str_enum
from app.models.enums import OpeningSource
from app.models.mixins import IdPrimaryKeyMixin, TimestampMixin


class Opening(IdPrimaryKeyMixin, TimestampMixin, Base):
    """An opening identified by a source-specific identifier.

    A row exists only when the source supplied a usable identifier. Games without
    reliable opening data keep ``games.opening_id`` NULL and are grouped as
    "Unknown" by the analytics layer; no placeholder opening row is created.
    """

    __tablename__ = "openings"
    __table_args__ = (
        UniqueConstraint("source", "source_opening_id"),
        CheckConstraint("char_length(source_opening_id) > 0", name="source_opening_id_not_empty"),
        CheckConstraint("char_length(name) > 0", name="name_not_empty"),
        CheckConstraint("eco_code IS NULL OR eco_code ~ '^[A-E][0-9]{2}$'", name="eco_code_format"),
        Index(None, "eco_code"),
    )

    source: Mapped[OpeningSource] = mapped_column(
        str_enum(OpeningSource, "opening_source"), nullable=False
    )
    source_opening_id: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    eco_code: Mapped[str | None] = mapped_column(String(3))

    def __repr__(self) -> str:
        return f"Opening(id={self.id!r}, name={self.name!r})"
