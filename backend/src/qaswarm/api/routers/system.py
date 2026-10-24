"""System capabilities: what this local runtime can and cannot do right now.

Not part of the v1 contract table (recorded as a deviation). Values are derived from live
configuration and connectivity; nothing is fabricated and no secret is ever returned.
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


class Capability(BaseModel):
    available: bool
    status: str
    planned_slice: str | None = None


class CapabilitiesOut(BaseModel):
    product: str = "RaOne"
    version: str
    local_only: bool = True
    external_ai_providers: str = "disabled"
    telemetry_export: str = "none"
    auth_mode: str
    database: Capability
    storage: dict[str, Any]
    execution_service: Capability
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
    return CapabilitiesOut(
        version=__version__,
        auth_mode="dev-headers" if settings.dev_auth else "none (OIDC arrives in slice 3e)",
        database=db,
        storage={
            "driver": url.drivername,
            "host": url.host or "",
            "port": url.port or 5432,
            "database": url.database or "",
        },
        execution_service=Capability(
            available=False, status="not implemented in this phase", planned_slice="1c"
        ),
        evidence_store=Capability(
            available=False, status="not implemented in this phase", planned_slice="1b"
        ),
        model_gateway=Capability(
            available=False,
            status="not configured; local models only by design",
            planned_slice="2c",
        ),
        test_engines=[],
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
