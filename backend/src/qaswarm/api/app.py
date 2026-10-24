"""FastAPI application factory."""

from __future__ import annotations

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from qaswarm import __version__
from qaswarm.api.errors import install_error_handlers
from qaswarm.api.middleware import CorrelationIdMiddleware
from qaswarm.api.routers import health, jobs, projects, repositories, stubs
from qaswarm.config import Settings, get_settings
from qaswarm.telemetry.logging import configure_logging

API_PREFIX = "/api/v1"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="RaOne API",
        version=__version__,
        description=(
            "RaOne — Autonomous AI-Powered QA Platform. Control-plane API. Slice 1a: projects, "
            "repository registration (syntactic validation), "
            "job creation with idempotency and duplicate prevention, cancel, SSE events. Every other "
            "contract endpoint returns 501 with its planned slice. The control plane never executes "
            "repository code."
        ),
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
    )
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["ETag", "Location", "X-Correlation-ID", "Idempotent-Replayed"],
    )
    app.add_middleware(CorrelationIdMiddleware)
    install_error_handlers(app)

    app.include_router(health.router)
    api = APIRouter(prefix=API_PREFIX)
    api.include_router(projects.router)
    api.include_router(repositories.router)
    api.include_router(jobs.router)
    api.include_router(stubs.router)
    app.include_router(api)
    return app
