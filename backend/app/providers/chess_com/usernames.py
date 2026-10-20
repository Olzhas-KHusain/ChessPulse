"""Chess.com username normalization.

Chess.com usernames are case-insensitive; the API addresses players by lowercase
username. The official documentation does not publish the exact character rules,
so the accepted pattern is a deliberately conservative *safe superset*: ASCII
letters, digits, underscore and hyphen. Anything else (slashes, dots, spaces,
percent signs, non-ASCII) is rejected before it can reach a URL path.
"""

from __future__ import annotations

import re

USERNAME_MAX_LENGTH = 64  # matches players.username (VARCHAR(64))
_USERNAME_RE = re.compile(r"^[a-z0-9_-]{1,64}$")


class InvalidUsernameError(ValueError):
    """The username is empty, too long, or contains unsupported characters."""


def normalize_username(raw: str) -> str:
    """Return the normalized (trimmed, lowercase) username or raise ``InvalidUsernameError``."""
    if not isinstance(raw, str):
        raise InvalidUsernameError("username must be a string")
    candidate = raw.strip().lower()
    if not _USERNAME_RE.fullmatch(candidate):
        raise InvalidUsernameError(
            "username must be 1-64 characters: letters, digits, underscore or hyphen"
        )
    return candidate


def try_normalize_username(raw: object) -> str | None:
    """Normalize an untrusted value from a provider payload; ``None`` if unusable."""
    if not isinstance(raw, str):
        return None
    try:
        return normalize_username(raw)
    except InvalidUsernameError:
        return None
