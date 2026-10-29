"""Environment-based application settings.

Settings are validated once at startup. Validation failures are reported as a
:class:`ConfigurationError` that names the offending variables but never echoes
their values, so credentials cannot leak into logs or terminals.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from app import __version__

# backend/app/core/config.py -> the repository root is three levels above this package.
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ENV_FILE = REPO_ROOT / ".env"

AppEnv = Literal["development", "test", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class ConfigurationError(RuntimeError):
    """Raised when required configuration is missing or invalid.

    The message is safe to show to an operator: it lists variable names and
    reasons only, never configuration values.
    """


class Settings(BaseSettings):
    """Application settings loaded from environment variables and an optional .env file."""

    model_config = SettingsConfigDict(
        env_file=DEFAULT_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        # .env also holds POSTGRES_* and VITE_* variables used by other tools.
        extra="ignore",
    )

    app_env: AppEnv = "development"
    log_level: LogLevel = "INFO"
    database_url: SecretStr
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]

    # --- Chess.com provider -----------------------------------------------------
    # Chess.com recommends a recognizable User-Agent that includes contact information.
    chess_com_user_agent: str = f"ChessPulse/{__version__}"
    # Per-phase HTTP timeout (connect, read, write, pool) for each upstream request.
    upstream_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    # Additional attempts after the first one, for transient failures only.
    upstream_max_retries: int = Field(default=2, ge=0, le=5)
    # Longest Retry-After / backoff delay we are willing to wait inside one request.
    upstream_max_retry_after_seconds: float = Field(default=10.0, ge=0, le=120)

    # --- Cache policy -----------------------------------------------------------
    # How long a successfully refreshed player dataset is served without contacting
    # the provider. Chess.com documents that PubAPI data refreshes at most every 12 h.
    cache_ttl_seconds: int = Field(default=12 * 3600, ge=60, le=7 * 24 * 3600)
    # Minimum wait after a failed refresh before the next attempt (Retry-After wins
    # when longer), so outages and rate limits are not hammered.
    refresh_failure_cooldown_seconds: int = Field(default=300, ge=0, le=24 * 3600)

    # --- Engine analysis --------------------------------------------------------
    # Absolute path to a Stockfish binary. Empty means "look for `stockfish` on PATH".
    stockfish_path: str = ""
    # Fixed-depth profile. Depth 12 is fast enough for a background worker and
    # deep enough to separate ordinary inaccuracies from real blunders.
    analysis_depth: int = Field(default=12, ge=6, le=30)
    analysis_threads: int = Field(default=1, ge=1, le=64)
    analysis_hash_mb: int = Field(default=64, ge=16, le=4096)
    analysis_move_timeout_seconds: float = Field(default=30.0, gt=0, le=600)
    # Claims after which a repeatedly failing job stays failed until re-requested.
    analysis_job_max_attempts: int = Field(default=3, ge=1, le=10)
    analysis_worker_poll_seconds: float = Field(default=2.0, ge=0.1, le=60)
    # A job left running longer than this is assumed to belong to a dead worker.
    analysis_stale_job_minutes: int = Field(default=30, ge=1, le=24 * 60)

    @field_validator("database_url")
    @classmethod
    def _validate_database_url(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        try:
            url = make_url(raw)
        except ArgumentError:
            raise ValueError(
                "must be a valid SQLAlchemy URL, e.g. "
                "postgresql+psycopg://user:password@localhost:5432/dbname"
            ) from None
        if url.get_backend_name() != "postgresql":
            raise ValueError(
                "must use a PostgreSQL URL (scheme 'postgresql' or 'postgresql+psycopg')"
            )
        if not url.database:
            raise ValueError("must include a database name")
        return value

    @field_validator("chess_com_user_agent")
    @classmethod
    def _validate_user_agent(cls, value: str) -> str:
        value = value.strip()
        if not 1 <= len(value) <= 256 or not all(" " <= ch <= "~" for ch in value):
            raise ValueError("must be 1-256 printable ASCII characters")
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("cors_origins")
    @classmethod
    def _validate_cors_origins(cls, value: list[str]) -> list[str]:
        for origin in value:
            if origin == "*" or not origin.startswith(("http://", "https://")):
                raise ValueError(
                    "must be a comma-separated list of explicit http(s) origins (no wildcard)"
                )
        return value


def load_settings(env_file: str | Path | None = DEFAULT_ENV_FILE) -> Settings:
    """Load and validate settings, raising :class:`ConfigurationError` on failure.

    Args:
        env_file: Path to a dotenv file, or ``None`` to read only the process environment.
    """
    try:
        return Settings(_env_file=env_file)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in err['loc']).upper() or 'settings'}: {err['msg']}"
            for err in exc.errors(include_input=False, include_url=False, include_context=False)
        )
        raise ConfigurationError(
            f"Invalid configuration ({problems}). "
            "Copy .env.example to .env and set the listed variables."
        ) from None


@lru_cache
def get_settings() -> Settings:
    """Return process-wide settings (loaded once, validated at first use)."""
    return load_settings()
