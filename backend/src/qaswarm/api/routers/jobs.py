from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from qaswarm.api.auth import WRITE_ROLES, Principal, get_principal, require_role
from qaswarm.api.deps import get_db
from qaswarm.api.errors import Problem
from qaswarm.api.etag import etag_for, parse_if_match
from qaswarm.api.pagination import clamp_limit, decode_cursor
from qaswarm.api.schemas import (
    CheckRunOut,
    CompareOut,
    JobCancelOut,
    JobCancelRequest,
    JobCreate,
    JobDetailOut,
    JobOut,
    Paginated,
    WorkerRunOut,
)
from qaswarm.api.services import jobs as svc
from qaswarm.api.services import results as results_svc
from qaswarm.config import Settings, get_settings
from qaswarm.telemetry.logging import correlation_id_var

router = APIRouter(prefix="/jobs", tags=["jobs"])

_PRINTABLE_ASCII = set(range(0x21, 0x7F))


def _validate_key(key: str | None) -> str:
    if key is None or key == "":
        raise Problem(
            400,
            "idempotency_key_required",
            "POST /jobs requires an Idempotency-Key header (1-128 printable ASCII).",
        )
    if len(key) > 128 or any(ord(c) not in _PRINTABLE_ASCII for c in key):
        raise Problem(
            400, "bad_request", "Idempotency-Key must be 1-128 printable ASCII characters."
        )
    return key


@router.post(
    "",
    status_code=202,
    response_model=JobOut,
    responses={
        400: {"description": "idempotency_key_required"},
        409: {"description": "job_duplicate_active"},
        422: {"description": "validation_failed / idempotency_key_reused"},
    },
)
def create_job(
    body: JobCreate,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: Session = Depends(get_db),
    principal: Principal = require_role(*WRITE_ROLES),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    key = _validate_key(idempotency_key)
    replay = svc.find_idempotent_replay(session, principal, key, body)
    if replay is not None:
        headers = {**replay.response_headers, "Idempotent-Replayed": "true"}
        return JSONResponse(
            status_code=replay.status_code, content=replay.response_body, headers=headers
        )
    status_code, out = svc.create_job(
        session,
        principal,
        body,
        idempotency_key=key,
        settings=settings,
        correlation_id=correlation_id_var.get(),
    )
    return JSONResponse(
        status_code=status_code,
        content=out,
        headers={
            "Location": f"/api/v1/jobs/{out['id']}",
            "ETag": etag_for(out["id"], out["version"]),
        },
    )


@router.get("", response_model=Paginated[JobOut])
def list_jobs(
    state: str | None = Query(default=None, description="Comma-separated job states"),
    repository_id: str | None = None,
    project_id: str | None = None,
    limit: int | None = Query(default=None, ge=1, le=200),
    cursor: str | None = None,
    session: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> Paginated[JobOut]:
    lim = clamp_limit(limit)
    states = [s.strip() for s in state.split(",") if s.strip()] if state else None
    items, next_cursor = svc.list_jobs(
        session,
        principal,
        states=states,
        repository_id=repository_id,
        project_id=project_id,
        limit=lim,
        after=decode_cursor(cursor),
    )
    return Paginated(items=items, next_cursor=next_cursor, limit=lim)


@router.get("/{job_id}", response_model=JobDetailOut)
def get_job(
    job_id: str,
    response: Response,
    session: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> JobDetailOut:
    job = svc.get_job_row(session, principal, job_id)
    response.headers["ETag"] = etag_for(job.id, job.version)
    return svc.to_detail(session, job)


@router.post(
    "/{job_id}/cancel",
    status_code=202,
    response_model=JobCancelOut,
    responses={409: {"description": "invalid_state_transition"}},
)
def cancel_job(
    job_id: str,
    body: JobCancelRequest | None = None,
    if_match: str | None = Header(default=None, alias="If-Match"),
    session: Session = Depends(get_db),
    principal: Principal = require_role(*WRITE_ROLES),
) -> JobCancelOut:
    reason = body.reason if body else None
    return svc.cancel_job(
        session,
        principal,
        job_id,
        reason,
        parse_if_match(if_match, job_id),
        correlation_id_var.get(),
    )


@router.get("/{job_id}/checks", response_model=list[CheckRunOut])
def list_checks(
    job_id: str,
    session: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> list[CheckRunOut]:
    return results_svc.list_checks(session, principal, job_id)


@router.get("/{job_id}/worker-runs", response_model=list[WorkerRunOut])
def list_worker_runs(
    job_id: str,
    session: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> list[WorkerRunOut]:
    return results_svc.list_worker_runs(session, principal, job_id)


@router.get("/{job_id}/compare", response_model=CompareOut)
def compare_jobs(
    job_id: str,
    with_job: str = Query(alias="with", description="Job id to compare against"),
    session: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> CompareOut:
    return results_svc.compare_jobs(session, principal, job_id, with_job)


@router.get(
    "/{job_id}/events",
    summary="Server-Sent Events stream of job events",
    response_class=StreamingResponse,
)
def job_events(
    job_id: str,
    request: Request,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    session: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    job = svc.get_job_row(session, principal, job_id)
    resume = last_event_id or request.query_params.get("last_event_id")
    stream = svc.job_event_stream(
        job.id,
        principal.org_id,
        last_event_id=resume,
        heartbeat_seconds=settings.sse_heartbeat_seconds,
    )
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
