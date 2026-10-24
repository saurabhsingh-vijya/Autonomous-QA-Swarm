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
    # Deployment environment label; anything other than "dev" / "test" makes the dev conveniences
    # above show up as warnings (they are never silently refused, so a demo still boots).
    environment: str = "dev"

    @property
    def is_dev(self) -> bool:
        return self.environment.lower() in {"dev", "development", "local", "test"}

    def startup_warnings(self) -> list[str]:
        """Human-readable warnings about incomplete or unsafe configuration (phase 6).

        Logged once at startup and exposed in ``GET /system/capabilities`` so operators and the UI
        can see what this deployment can and cannot be trusted with.
        """
        w: list[str] = []
        if self.dev_auth:
            w.append(
                "AQS_DEV_AUTH=true: anyone who can reach the API can pick a user and a role via "
                "X-Dev-User / X-Dev-Role. Local development only; OIDC arrives in slice 3e."
            )
        else:
            w.append(
                "AQS_DEV_AUTH=false and no OIDC provider in this build: every /api/v1 call returns "
                "401. Set AQS_DEV_AUTH=true for local development."
            )
        if "qaswarm-dev-only" in self.database_url:
            w.append("The database URL uses the sample password 'qaswarm-dev-only'.")
        if not self.exec_token:
            w.append(
                "AQS_EXEC_TOKEN is not set: the Execution Service API answers 503 and no task will "
                "ever run."
            )
        elif len(self.exec_token) < 16:
            w.append("AQS_EXEC_TOKEN is shorter than 16 characters; use a long random secret.")
        if self.exec_allow_unsandboxed_code_execution:
            w.append(
                "AQS_EXEC_ALLOW_UNSANDBOXED_CODE_EXECUTION=true: repository test suites run in a "
                "plain subprocess on the worker host. This is NOT a sandbox (SEC-003/SEC-004)."
            )
        if self.embedded_exec_worker:
            w.append(
                "AQS_EMBEDDED_EXEC_WORKER=true: the Execution Service runs inside the API process "
                "and shares its host, network and file system. Local development only."
            )
        if self.embedded_scheduler:
            w.append("AQS_EMBEDDED_SCHEDULER=true: scheduler runs inside the API process.")
        if self.dev_fixture_repos:
            w.append(
                "AQS_DEV_FIXTURE_REPOS=true: https://fixtures.local/<name> URLs are served from "
                f"the local directory {self.fixtures_dir!r}. Dev-only, labelled as such."
            )
        if not self.intake_dns_check:
            w.append("AQS_INTAKE_DNS_CHECK=false: private-address rejection (SEC-002) is off.")
        if "*" in self.cors_origins:
            w.append("AQS_CORS_ORIGINS contains '*'.")
        if not self.is_dev:
            unsafe = [
                flag
                for flag, on in (
                    ("AQS_DEV_AUTH", self.dev_auth),
                    ("AQS_DEV_FIXTURE_REPOS", self.dev_fixture_repos),
                    ("AQS_EMBEDDED_EXEC_WORKER", self.embedded_exec_worker),
                    (
                        "AQS_EXEC_ALLOW_UNSANDBOXED_CODE_EXECUTION",
                        self.exec_allow_unsandboxed_code_execution,
                    ),
                )
                if on
            ]
            if unsafe:
                w.append(
                    f"AQS_ENVIRONMENT={self.environment!r} but development flags are on: "
                    + ", ".join(unsafe)
                    + ". This deployment must not be exposed to untrusted users."
                )
        return w


@lru_cache
def get_settings() -> Settings:
    return Settings()
