"""Persistence for ``openings``."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import func, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Opening, OpeningSource
from app.repositories._batching import chunked

OpeningKey = tuple[OpeningSource, str]


@dataclass(frozen=True, slots=True)
class OpeningRecord:
    """An opening identified by its source. ``eco_code`` is None when not supplied."""

    source: OpeningSource
    source_opening_id: str
    name: str
    eco_code: str | None = None

    @property
    def key(self) -> OpeningKey:
        return (self.source, self.source_opening_id)


class OpeningRepository:
    """Data access for openings. Methods never commit."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def ensure_openings(self, records: Iterable[OpeningRecord]) -> dict[OpeningKey, int]:
        """Upsert openings by ``(source, source_opening_id)`` and return their ids.

        A later record for the same key replaces ``name`` and ``eco_code``, except
        that a known ECO code is never erased by a record that lacks one.
        """
        by_key = {record.key: record for record in records}  # last record wins
        if not by_key:
            return {}

        ids: dict[OpeningKey, int] = {}
        for batch in chunked(list(by_key.values())):
            stmt = insert(Opening).values(
                [
                    {
                        "source": r.source,
                        "source_opening_id": r.source_opening_id,
                        "name": r.name,
                        "eco_code": r.eco_code,
                    }
                    for r in batch
                ]
            )
            new_eco = func.coalesce(stmt.excluded.eco_code, Opening.eco_code)
            stmt = stmt.on_conflict_do_update(
                index_elements=[Opening.source, Opening.source_opening_id],
                set_={"name": stmt.excluded.name, "eco_code": new_eco, "updated_at": func.now()},
                where=tuple_(Opening.name, Opening.eco_code).is_distinct_from(
                    tuple_(stmt.excluded.name, new_eco)
                ),
            )
            self._session.execute(stmt)
            rows = self._session.execute(
                select(Opening.source, Opening.source_opening_id, Opening.id).where(
                    tuple_(Opening.source, Opening.source_opening_id).in_([r.key for r in batch])
                )
            )
            ids.update({(source, sid): oid for source, sid, oid in rows})
        return ids
