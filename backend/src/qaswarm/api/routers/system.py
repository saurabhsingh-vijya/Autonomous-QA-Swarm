"""System capabilities and the agent registry: what this local runtime can and cannot do.

Values are derived from live configuration and connectivity; nothing is fabricated and no secret
is ever returned. ``/system/capabilities`` is recorded as a deviation from the v1 contract table.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import make_url

from qaswarm import __version__
from qaswarm.api.auth import Principal, get_principal
from qaswarm.config import Settings, get_settings
from qaswarm.db.session import get_engine

router = APIRouter(prefix="/system", tags=["system"])

ENGINES = ["snapshot_integrity", "python_syntax", "secret_scan", "pytest"]


class Capability(BaseModel):
    available: bool
    status: str
    planned_slice: str | None = None


class CapabilitiesOut(BaseModel):
    product: str = "RaOne"
    version: str
    phase: str
    local_only: bool = True
    external_ai_providers: str = "disabled"
    llm_provider: str
    telemetry_export: str = "none"
    auth_mode: str
    database: Capability
    storage: dict[str, Any]
    execution_service: Capability
    execution_enabled: bool
    repository_code_execution_allowed: bool
    sandbox: str
    dev_fixture_repos: bool
    embedded_scheduler: bool
    embedded_exec_worker: bool
    agent_runner_enabled: bool
    engines: list[str]
    evidence_store: Capability
    model_gateway: Capability
    test_engines: list[str]
    integrations: dict[str, Capability]
    limits: dict[str, int]


@router.get("/capabilities", response_model=CapabilitiesOut, summary="Local runtime capabilities")
def capabilities(
    principal: Principal = Depends(get_principal),
    settings: Settings = Depends(get_settings),
) -> CapabilitiesOut:
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        db = Capability(available=True, status="reachable")
    except Exception:
        db = Capability(available=False, status="unreachable")
    url = make_url(settings.database_url)
    execution_enabled = bool(settings.exec_token)
    return CapabilitiesOut(
        version=__version__,
        phase="2 execution engine + 3 orchestration + 5 defect intelligence",
        llm_provider=settings.llm_provider,
        auth_mode="dev-headers" if settings.dev_auth else "none (OIDC arrives in slice 3e)",
        database=db,
        storage={
            "driver": url.drivername,
            "host": url.host or "",
            "port": url.port or 5432,
            "database": url.database or "",
        },
        execution_service=Capability(
            available=execution_enabled,
            status=(
                "process runtime (no gVisor/Docker on this build); exec hosts lease over "
                "/internal/v1/exec with AQS_EXEC_TOKEN"
                if execution_enabled
                else "disabled: AQS_EXEC_TOKEN is not set; repository checks are not planned"
            ),
            planned_slice=None if execution_enabled else "1c",
        ),
        execution_enabled=execution_enabled,
        repository_code_execution_allowed=settings.exec_allow_unsandboxed_code_execution,
        sandbox="process (no gVisor/Docker on this build)",
        dev_fixture_repos=settings.dev_fixture_repos,
        embedded_scheduler=settings.embedded_scheduler,
        embedded_exec_worker=settings.embedded_exec_worker,
        agent_runner_enabled=settings.runner_enabled,
        engines=ENGINES,
        evidence_store=Capability(
            available=True,
            status=f"local content-addressed store at {settings.evidence_dir}; "
            "agent evidence is kept inline in the database",
        ),
        model_gateway=Capability(
            available=settings.llm_provider != "none",
            status=(
                f"local provider '{settings.llm_provider}' ({settings.llm_model})"
                if settings.llm_provider != "none"
                else "not configured; deterministic adapters only"
            ),
            planned_slice=None,
        ),
        test_engines=ENGINES if execution_enabled else [],
        integrations={
            name: Capability(available=False, status="not connected", planned_slice="3e")
            for name in ("github", "gitlab", "jenkins", "github_actions", "slack", "teams")
        },
        limits={
            "job_wall_clock_seconds": settings.job_wall_clock_seconds,
            "task_wall_clock_seconds": settings.task_wall_clock_seconds,
            "lease_ttl_seconds": settings.lease_ttl_seconds,
            "heartbeat_seconds": settings.heartbeat_seconds,
            "task_max_retries": settings.task_max_retries,
        },
    )
