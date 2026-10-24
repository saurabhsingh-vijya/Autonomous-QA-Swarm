"""FastAPI application factory."""

from __future__ import annotations

import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from qaswarm import __version__
from qaswarm.api.errors import install_error_handlers
from qaswarm.api.middleware import CorrelationIdMiddleware
from qaswarm.api.routers import (
    audit,
    evidence,
    exec_internal,
    health,
    jobs,
    projects,
    repositories,
    stubs,
    system,
    targets,
)
from qaswarm.config import Settings, get_settings
from qaswarm.telemetry.logging import configure_logging

API_PREFIX = "/api/v1"
log = logging.getLogger("qaswarm.api.app")


def _start_embedded_roles(settings: Settings, stop: threading.Event) -> list[threading.Thread]:
    """Local-development convenience: run the scheduler and one exec worker in-process."""
    threads: list[threading.Thread] = []
    if settings.embedded_scheduler:
        from qaswarm.workflow.scheduler import Scheduler

        t = threading.Thread(
            target=Scheduler(settings).run_forever, args=(stop,), name="aqs-scheduler", daemon=True
        )
        threads.append(t)
    if settings.embedded_exec_worker:
        if not settings.exec_token:
            log.warning("embedded exec worker not started: AQS_EXEC_TOKEN is not set")
        else:
            from qaswarm_exec.host.runner import run_embedded

            t = threading.Thread(
                target=run_embedded,
                kwargs={
                    "control_plane_url": settings.exec_control_plane_url,
                    "token": settings.exec_token,
                    "allow_code_execution": settings.exec_allow_unsandboxed_code_execution,
                    "fixtures_dir": settings.fixtures_dir if settings.dev_fixture_repos else None,
                    "stop": stop,
                },
                name="aqs-exec-worker",
                daemon=True,
            )
            threads.append(t)
    for t in threads:
        t.start()
    return threads


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        stop = threading.Event()
        threads = _start_embedded_roles(settings, stop)
        try:
            yield
        finally:
            stop.set()
            for t in threads:
                t.join(timeout=10)

    app = FastAPI(
        title="Autonomous QA Swarm API",
        version=__version__,
        description=(
            "Control-plane API. Phase 2: projects, repositories, idempotent job creation, Intake & "
            "Pinning (git ls-remote), template planning, task leasing for the Execution Service, "
            "check runs, test executions, evidence, reports, run comparison and the audit trail. "
            "Phase 4: target environments with HA-01 attestations, API/browser/security/performance "
            "checks against authorised targets, and regression reruns. "
            "Endpoints not built yet return 501 with their planned slice. The control plane never "
            "executes repository code."
        ),
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[
            "ETag",
            "Location",
            "X-Correlation-ID",
            "Idempotent-Replayed",
            "X-Test-Counts",
        ],
    )
    app.add_middleware(CorrelationIdMiddleware)
    install_error_handlers(app)

    app.include_router(health.router)
    app.include_router(exec_internal.router)
    api = APIRouter(prefix=API_PREFIX)
    api.include_router(projects.router)
    api.include_router(repositories.router)
    api.include_router(targets.router)
    api.include_router(jobs.router)
    api.include_router(evidence.router)
    api.include_router(audit.router)
    api.include_router(system.router)
    api.include_router(stubs.router)
    app.include_router(api)
    return app
