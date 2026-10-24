"""Application settings (pydantic-settings, ``AQS_`` prefix). No secrets have defaults."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AQS_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = "postgresql+psycopg://qaswarm:qaswarm-dev-only@localhost:5432/qaswarm"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    log_level: str = "INFO"
    dev_auth: bool = False
    problem_type_base: str = "https://raone.dev/problems/"
    git_host_allowlist: list[str] = Field(default_factory=lambda: ["github.com", "gitlab.com"])

    # Job defaults (LLD): wall clock 4 h (max 12 h), task 30 min (max 2 h), lease 90 s,
    # heartbeat 30 s, 2 retries, backoff 30 s / 120 s with ±20 % jitter.
    job_wall_clock_seconds: int = 4 * 3600
    job_wall_clock_max_seconds: int = 12 * 3600
    task_wall_clock_seconds: int = 30 * 60
    task_wall_clock_max_seconds: int = 2 * 3600
    lease_ttl_seconds: int = 90
    heartbeat_seconds: int = 30
    task_max_retries: int = 2
    backoff_seconds: list[int] = Field(default_factory=lambda: [30, 120])
    backoff_jitter: float = 0.2
    idempotency_ttl_hours: int = 24
    sse_heartbeat_seconds: int = 15


@lru_cache
def get_settings() -> Settings:
    return Settings()
