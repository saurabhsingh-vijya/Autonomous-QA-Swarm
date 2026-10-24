"""Narrow internal API for the Execution Service (not under ``/api/v1``; token-authenticated).

The Execution Service leases, heartbeats, uploads evidence and reports results here. It has no
database access. Every call needs ``X-Exec-Token`` equal to ``AQS_EXEC_TOKEN``; with the token
unset the whole surface answers 503 so execution cannot be enabled by accident.
"""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from qaswarm.api.deps import get_db, get_evidence_store
from qaswarm.api.errors import Problem
from qaswarm.api.exec_schemas import (
    EvidenceUpload,
    EvidenceUploaded,
    FailureSubmit,
    HeartbeatRequest,
    HeartbeatResponse,
    LeaseRequest,
    LeaseResponse,
    ResultSubmit,
    TaskStateOut,
    WorkerRunCreate,
    WorkerRunCreated,
    WorkerRunDestroyed,
)
from qaswarm.api.services import execution as svc
from qaswarm.config import Settings, get_settings
from qaswarm.evidence import EvidenceStore
from qaswarm.workflow.queue import TaskQueue

router = APIRouter(prefix="/internal/v1/exec", tags=["execution service (internal)"])


def require_exec_token(
    x_exec_token: str | None = Header(default=None, alias="X-Exec-Token"),
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.exec_token:
        raise Problem(
            503,
            "dependency_unavailable",
            "The Execution Service API is disabled: AQS_EXEC_TOKEN is not configured.",
        )
    if not x_exec_token or not hmac.compare_digest(x_exec_token, settings.exec_token):
        raise Problem(401, "unauthenticated", "Invalid or missing X-Exec-Token.")


def get_queue(settings: Settings = Depends(get_settings)) -> TaskQueue:
    return TaskQueue(settings)


@router.post("/lease", response_model=LeaseResponse, dependencies=[Depends(require_exec_token)])
def lease(
    body: LeaseRequest,
    session: Session = Depends(get_db, scope="function"),
    queue: TaskQueue = Depends(get_queue),
    settings: Settings = Depends(get_settings),
) -> LeaseResponse:
    return LeaseResponse(tasks=svc.lease_tasks(session, queue, body, settings))


@router.post(
    "/tasks/{task_id}/heartbeat",
    response_model=HeartbeatResponse,
    dependencies=[Depends(require_exec_token)],
)
def heartbeat(
    task_id: str,
    body: HeartbeatRequest,
    session: Session = Depends(get_db, scope="function"),
    queue: TaskQueue = Depends(get_queue),
) -> HeartbeatResponse:
    state, expires = svc.heartbeat(session, queue, task_id, body.worker_id)
    return HeartbeatResponse(task_id=task_id, state=state, lease_expires_at=expires)


@router.post(
    "/tasks/{task_id}/worker-runs",
    response_model=WorkerRunCreated,
    status_code=201,
    dependencies=[Depends(require_exec_token)],
)
def create_worker_run(
    task_id: str, body: WorkerRunCreate, session: Session = Depends(get_db, scope="function")
) -> WorkerRunCreated:
    run = svc.create_worker_run(session, task_id, body)
    return WorkerRunCreated(worker_run_id=run.id)


@router.post(
    "/worker-runs/{worker_run_id}/destroyed",
    response_model=TaskStateOut,
    dependencies=[Depends(require_exec_token)],
)
def destroy_worker_run(
    worker_run_id: str,
    body: WorkerRunDestroyed,
    session: Session = Depends(get_db, scope="function"),
) -> TaskStateOut:
    run = svc.destroy_worker_run(session, worker_run_id, body)
    return TaskStateOut(task_id=run.task_id, state="destroyed")


@router.post(
    "/tasks/{task_id}/evidence",
    response_model=EvidenceUploaded,
    status_code=201,
    dependencies=[Depends(require_exec_token)],
)
def upload_evidence(
    task_id: str,
    body: EvidenceUpload,
    session: Session = Depends(get_db, scope="function"),
    store: EvidenceStore = Depends(get_evidence_store),
) -> EvidenceUploaded:
    return svc.upload_evidence(session, store, task_id, body)


@router.post(
    "/tasks/{task_id}/result",
    response_model=TaskStateOut,
    dependencies=[Depends(require_exec_token)],
    responses={422: {"description": "worker_result_invalid (attempt failed, E-EXEC-004)"}},
)
def submit_result(
    task_id: str,
    body: ResultSubmit,
    session: Session = Depends(get_db, scope="function"),
    queue: TaskQueue = Depends(get_queue),
) -> TaskStateOut:
    return TaskStateOut(task_id=task_id, state=svc.submit_result(session, queue, task_id, body))


@router.post(
    "/tasks/{task_id}/fail", response_model=TaskStateOut, dependencies=[Depends(require_exec_token)]
)
def submit_failure(
    task_id: str,
    body: FailureSubmit,
    session: Session = Depends(get_db, scope="function"),
    queue: TaskQueue = Depends(get_queue),
) -> TaskStateOut:
    return TaskStateOut(task_id=task_id, state=svc.submit_failure(session, queue, task_id, body))
