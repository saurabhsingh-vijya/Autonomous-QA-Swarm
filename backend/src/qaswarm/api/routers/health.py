from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from qaswarm import __version__
from qaswarm.api.errors import problem_response
from qaswarm.api.schemas import HealthOut, ReadyOut
from qaswarm.db.session import get_engine

router = APIRouter(tags=["health"])
log = logging.getLogger(__name__)


@router.get("/healthz", response_model=HealthOut, summary="Liveness")
def healthz() -> HealthOut:
    return HealthOut(status="ok", version=__version__)


@router.get(
    "/readyz",
    response_model=ReadyOut,
    summary="Readiness (database reachable)",
    responses={503: {"description": "Database unreachable (problem+json)"}},
)
def readyz(request: Request) -> ReadyOut | JSONResponse:
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        log.exception("readiness check failed")
        return problem_response(
            request, 503, "dependency_unavailable", "The database is not reachable."
        )
    return ReadyOut(status="ok", version=__version__, database="reachable")
