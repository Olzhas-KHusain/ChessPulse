"""Eligibility rule for the analytics dataset (spec §6.1-6.3).

A normalized provider game is eligible when all of the following hold:

1. ``time_class`` is ``rapid``: the provider's documented classification. The raw
   ``time_control`` string is never used to infer the class.
2. ``rules`` is exactly ``chess``. Variants (chess960, crazyhouse, ...) have separate
   ratings; a missing ``rules`` value cannot be verified and is excluded.
3. ``played_at`` (the game end time) lies inside the shared analysis window.

Completion: monthly archives only contain finished games (PubAPI documentation), so
every archived game is complete. A game whose result could not be classified stays
eligible with result ``unknown``; it is never counted as a loss.
"""

from __future__ import annotations

from enum import StrEnum

from app.analytics.window import AnalysisWindow
from app.models.enums import TimeClass
from app.providers.types import ProviderGame


class IneligibleReason(StrEnum):
    NOT_RAPID = "not_rapid"
    VARIANT = "non_standard_variant"
    RULES_UNVERIFIED = "rules_unverified"
    OUTSIDE_WINDOW = "outside_window"


def ineligibility_reason(game: ProviderGame, window: AnalysisWindow) -> IneligibleReason | None:
    """Return why ``game`` is not eligible, or ``None`` when it is."""
    if game.time_class is not TimeClass.RAPID:
        return IneligibleReason.NOT_RAPID
    if game.rules is None:
        return IneligibleReason.RULES_UNVERIFIED
    if not game.is_standard_chess:
        return IneligibleReason.VARIANT
    if not window.contains(game.played_at):
        return IneligibleReason.OUTSIDE_WINDOW
    return None
