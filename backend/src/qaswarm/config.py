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
    problem_type_base: str = "https://qa-swarm.dev/problems/"
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

    # Phase 2: execution engine. The Execution Service (qaswarm_exec) authenticates to the narrow
    # internal API with this shared token; unset means the internal API refuses every call.
    exec_token: str | None = None
    # Content-addressed evidence objects live here (LLD key layout under this root).
    evidence_dir: str = "./data/evidence"
    evidence_inline_max_bytes: int = 1024 * 1024
    # Intake: DNS resolution + private-address rejection before git ls-remote (SEC-002).
    intake_dns_check: bool = True
    intake_timeout_seconds: int = 60
    # Dev-only fixture repositories (https://fixtures.local/<name>) resolved from a directory.
    dev_fixture_repos: bool = False
    fixtures_dir: str = "../exec/fixtures"
    # Scheduler role settings; the scheduler can also run inside the API process for local dev.
    scheduler_interval_seconds: float = 2.0
    embedded_scheduler: bool = False
    embedded_exec_worker: bool = False
    exec_control_plane_url: str = "http://127.0.0.1:8000"
    exec_allow_unsandboxed_code_execution: bool = False
    # Phase 4: controlled local-testing mode. Mirrors AQS_EXEC_ALLOW_LOCAL_TARGETS on the worker:
    # when false, targets whose host is a loopback/private address literal are refused at
    # registration (the worker refuses them again at connect time).
    allow_local_targets: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
