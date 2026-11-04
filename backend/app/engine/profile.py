"""Analysis configuration identity.

``profile_hash`` is the cache key component that makes results comparable: two
analyses share a hash only when they were produced with the same algorithm
version and search settings. The engine *version* is recorded in the result but
is not part of the hash, because it is only known after the process starts.
"""

from __future__ import annotations

import hashlib

PROFILE_VERSION = 1


def profile_hash(*, depth: int, threads: int, hash_mb: int) -> str:
    """Stable SHA-256 of the analysis profile."""
    material = (
        f"chesspulse-analysis-v{PROFILE_VERSION}"
        f"|engine=stockfish|depth={depth}|threads={threads}|hash={hash_mb}"
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()
