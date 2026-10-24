"""Build capabilities, so the UI can label honestly what this deployment can and cannot do."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from qaswarm import __version__
from qaswarm.api.auth import Principal, get_principal
from qaswarm.api.schemas import CapabilitiesOut
from qaswarm.config import Settings, get_settings

router = APIRouter(prefix="/system", tags=["system"])

ENGINES = ["snapshot_integrity", "python_syntax", "secret_scan", "pytest"]


@router.get("/capabilities", response_model=CapabilitiesOut)
def capabilities(
    settings: Settings = Depends(get_settings),
    principal: Principal = Depends(get_principal),
) -> CapabilitiesOut:
    return CapabilitiesOut(
        version=__version__,
        phase="2 — execution engine",
        execution_enabled=bool(settings.exec_token),
        repository_code_execution_allowed=settings.exec_allow_unsandboxed_code_execution,
        sandbox="process (no gVisor/Docker on this build)",
        dev_fixture_repos=settings.dev_fixture_repos,
        embedded_scheduler=settings.embedded_scheduler,
        embedded_exec_worker=settings.embedded_exec_worker,
        engines=ENGINES,
    )
