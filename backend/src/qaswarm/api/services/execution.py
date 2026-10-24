"""Control-plane side of the Execution Service protocol (phase 2).

The Execution Service never touches the database: it leases tasks, heartbeats, uploads evidence
and submits a schema-validated worker result through these functions (exposed under
``/internal/v1/exec``). Invalid worker results are rejected with ``E-EXEC-004`` and the attempt is
retried like an infrastructure error (docs/DECISIONS.md #7).
"""

from __future__ import annotations

import base64
import binascii
from datetime import UTC, datetime
from typing import Any

import jsonschema
from sqlalchemy import select
from sqlalchemy.orm import Session

from qaswarm.api.errors import Problem
from qaswarm.api.exec_schemas import (
    EvidenceUpload,
    EvidenceUploaded,
    FailureSubmit,
    LeasedTask,
    LeaseRequest,
    ResultSubmit,
    WorkerRunCreate,
    WorkerRunDestroyed,
)
from qaswarm.audit.chain import append_event
from qaswarm.config import Settings
from qaswarm.contracts import get_schema
from qaswarm.db.models import CheckRun, Job, OutboxEvent, Repository, Task, TestExecution, WorkerRun
from qaswarm.domain.enums import CheckOutcome, ErrorClass, TestExecutionStatus
from qaswarm.domain.ids import new_id
from qaswarm.evidence import EvidenceStore, store_evidence
from qaswarm.workflow.queue import LeaseLost, TaskQueue

_EXEC_TASK_TYPES = frozenset({"env_prepare", "check"})
_VALIDATOR = jsonschema.Draft202012Validator(get_schema("worker_result/1"))


def _now() -> datetime:
    return datetime.now(UTC)


def lease_tasks(
    session: Session, queue: TaskQueue, body: LeaseRequest, settings: Settings
) -> list[LeasedTask]:
    types = [t for t in body.task_types if t in _EXEC_TASK_TYPES]
    if not types:
        raise Problem(422, "validation_failed", "No leasable task types requested.")
    leases = queue.lease(session, body.worker_id, types, batch_size=body.batch_size)
    out: list[LeasedTask] = []
    for lease in leases:
        task = session.execute(select(Task).where(Task.id == lease.task_id)).scalar_one()
        job = session.execute(select(Job).where(Job.id == task.job_id)).scalar_one()
        repo = session.execute(
            select(Repository).where(Repository.id == job.repository_id)
        ).scalar_one()
        out.append(
            LeasedTask(
                task_id=task.id,
                attempt_id=lease.attempt_id,
                attempt_no=lease.attempt_no,
                job_id=job.id,
                org_id=job.org_id,
                job_display_id=job.display_id,
                stage=task.stage,
                task_type=task.task_type,
                inputs=task.inputs,
                lease_expires_at=lease.lease_expires_at,
                limits={
                    "task_wall_clock_seconds": settings.task_wall_clock_seconds,
                    "heartbeat_seconds": settings.heartbeat_seconds,
                    "output_cap_bytes": 50 * 1024 * 1024,
                },
                context={
                    "repository_url": repo.url,
                    "provider": repo.provider,
                    "ref": job.ref,
                    "commit_sha": job.commit_sha,
                    "snapshot_sha256": job.snapshot_sha256,
                    "profiles": job.profiles,
                },
            )
        )
    return out


def heartbeat(
    session: Session, queue: TaskQueue, task_id: str, worker_id: str
) -> tuple[str, datetime]:
    try:
        expires = queue.heartbeat(session, task_id, worker_id)
    except LeaseLost as exc:
        task = session.execute(select(Task.state).where(Task.id == task_id)).scalar_one_or_none()
        raise Problem(
            409,
            "lease_lost",
            "This worker no longer holds the lease for the task (E-QUEUE-002). Stop work and "
            "discard the result.",
            task_state=task,
            error_code_catalogue="E-QUEUE-002",
        ) from exc
    state = session.execute(select(Task.state).where(Task.id == task_id)).scalar_one()
    return state, expires


def _owned_task(session: Session, task_id: str, worker_id: str) -> Task:
    task = session.execute(
        select(Task).where(Task.id == task_id).with_for_update()
    ).scalar_one_or_none()
    if task is None:
        raise Problem(404, "not_found", "Task not found.")
    if task.lease_owner != worker_id or task.state not in ("leased", "running"):
        raise Problem(409, "lease_lost", "This worker does not hold the lease for the task.")
    return task


def create_worker_run(session: Session, task_id: str, body: WorkerRunCreate) -> WorkerRun:
    task = _owned_task(session, task_id, body.worker_id)
    run = WorkerRun(
        id=new_id("worker_run"),
        org_id=task.org_id,
        job_id=task.job_id,
        task_id=task.id,
        attempt_id=body.attempt_id,
        worker_id=body.worker_id,
        runtime=body.runtime,
        isolation=body.isolation,
        image_digest=body.image_digest,
        limits=body.limits,
        network_policy=body.network_policy,
        started_at=_now(),
    )
    session.add(run)
    session.flush()
    append_event(
        session,
        org_id=task.org_id,
        actor_type="service",
        actor_id=body.worker_id,
        action="worker_run.started",
        subject_type="worker_run",
        subject_id=run.id,
        job_id=task.job_id,
        details={"task_id": task.id, "runtime": body.runtime, "isolation": body.isolation},
    )
    return run


def destroy_worker_run(session: Session, worker_run_id: str, body: WorkerRunDestroyed) -> WorkerRun:
    """Record that a worker is gone. Never requires a live lease: destruction is always recordable."""
    run = session.execute(
        select(WorkerRun).where(WorkerRun.id == worker_run_id).with_for_update()
    ).scalar_one_or_none()
    if run is None:
        raise Problem(404, "not_found", "Worker run not found.")
    if run.destroyed_at is None:
        now = _now()
        run.ended_at = run.ended_at or now
        run.destroyed_at = now
        run.outcome = body.outcome
        run.exit_code = body.exit_code
        run.output_bytes = body.output_bytes
        run.truncated = body.truncated
        append_event(
            session,
            org_id=run.org_id,
            actor_type="service",
            actor_id=run.worker_id,
            action="worker_run.destroyed",
            subject_type="worker_run",
            subject_id=run.id,
            job_id=run.job_id,
            details={"outcome": body.outcome, "exit_code": body.exit_code},
        )
    return run


def upload_evidence(
    session: Session, store: EvidenceStore, task_id: str, body: EvidenceUpload
) -> EvidenceUploaded:
    task = _owned_task(session, task_id, body.worker_id)
    try:
        raw = base64.b64decode(body.content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise Problem(422, "validation_failed", "content_base64 is not valid base64.") from exc
    item = store_evidence(
        session,
        store,
        org_id=task.org_id,
        job_id=task.job_id,
        kind=body.kind,
        content=raw,
        media_type=body.media_type,
        producer=body.producer,
        label=body.label,
        task_id=task.id,
        worker_run_id=body.worker_run_id,
        deterministic=body.deterministic,
    )
    return EvidenceUploaded(
        evidence_id=item.id,
        sha256=item.sha256,
        size_bytes=item.size_bytes,
        redactions=item.redactions,
        truncated=item.truncated,
    )


def _validate_worker_result(result: dict[str, Any], task: Task) -> list[str]:
    errors = [e.message for e in sorted(_VALIDATOR.iter_errors(result), key=str)]
    if not errors and result.get("task_id") != task.id:
        errors.append("task_id does not match the leased task")
    if not errors and result.get("attempt_no") != task.attempt_count:
        errors.append("attempt_no does not match the current attempt")
    summary = result.get("summary", {})
    if not errors and isinstance(summary, dict):
        counted = sum(int(summary.get(k, 0)) for k in ("passed", "failed", "skipped", "errors"))
        if counted != int(summary.get("executed", 0)):
            errors.append("summary counters do not add up to executed")
    return errors


def _emit(session: Session, task: Task, event_type: str, payload: dict[str, Any]) -> None:
    session.add(
        OutboxEvent(
            id=new_id("outbox_event"),
            org_id=task.org_id,
            job_id=task.job_id,
            event_type=event_type,
            payload={"job_id": task.job_id, "task_id": task.id, **payload},
        )
    )


def submit_result(session: Session, queue: TaskQueue, task_id: str, body: ResultSubmit) -> str:
    task = _owned_task(session, task_id, body.worker_id)
    errors = _validate_worker_result(body.worker_result, task)
    if errors:
        queue.fail(
            session,
            task.id,
            body.worker_id,
            retryable=True,
            error_code="E-EXEC-004",
            error_class=ErrorClass.INFRASTRUCTURE_ERROR,
        )
        raise Problem(
            422,
            "worker_result_invalid",
            "The worker result failed schema or bounds validation (E-EXEC-004); the attempt was "
            "failed and will be retried within the retry budget.",
            errors=[{"pointer": "/worker_result", "code": "schema", "message": m} for m in errors],
        )
    valid_outcomes = {o.value for o in CheckOutcome}
    valid_statuses = {s.value for s in TestExecutionStatus}
    worker_run_id = str(body.worker_result.get("worker_run_id") or "") or None
    job = session.execute(select(Job).where(Job.id == task.job_id).with_for_update()).scalar_one()
    check_ids: dict[int, str] = {}
    for idx, c in enumerate(body.check_runs):
        if c.outcome not in valid_outcomes:
            raise Problem(422, "validation_failed", f"Unknown check outcome '{c.outcome}'.")
        run = CheckRun(
            id=new_id("check_run"),
            org_id=task.org_id,
            job_id=task.job_id,
            task_id=task.id,
            attempt_no=task.attempt_count,
            worker_run_id=worker_run_id,
            engine_id=c.engine_id,
            name=c.name,
            outcome=c.outcome,
            started_at=c.started_at,
            ended_at=c.ended_at,
            duration_ms=c.duration_ms,
            failure_message=c.failure_message,
            summary=c.summary,
            tool_name=c.tool_name,
            tool_version=c.tool_version,
            executes_repository_code=c.executes_repository_code,
            log_evidence_id=c.log_evidence_id,
            evidence={"items": list(c.evidence_ids)},
        )
        session.add(run)
        session.flush()
        check_ids[idx] = run.id
        _emit(
            session,
            task,
            "check.completed",
            {
                "check_run_id": run.id,
                "engine": run.engine_id,
                "name": run.name,
                "outcome": run.outcome,
                "duration_ms": run.duration_ms,
            },
        )
    primary_check = check_ids.get(0)
    if body.test_executions and primary_check is None:
        raise Problem(422, "validation_failed", "test_executions require at least one check_run.")
    tool_version = body.check_runs[0].tool_version if body.check_runs else "unknown"
    for t in body.test_executions:
        if t.status not in valid_statuses:
            raise Problem(422, "validation_failed", f"Unknown test status '{t.status}'.")
        session.add(
            TestExecution(
                id=new_id("test_execution"),
                org_id=task.org_id,
                job_id=task.job_id,
                task_id=task.id,
                check_run_id=primary_check or "",
                worker_run_id=worker_run_id,
                node_id=t.node_id,
                file=t.file,
                name=t.name,
                status=t.status,
                duration_ms=t.duration_ms,
                message=t.message,
                tool_version=tool_version,
                commit_sha=job.commit_sha,
            )
        )
    if body.snapshot_sha256 and task.task_type == "env_prepare":
        job.snapshot_sha256 = body.snapshot_sha256
        append_event(
            session,
            org_id=job.org_id,
            actor_type="service",
            actor_id=body.worker_id,
            action="snapshot.recorded",
            subject_type="job",
            subject_id=job.id,
            job_id=job.id,
            details={"snapshot_sha256": body.snapshot_sha256, "commit_sha": job.commit_sha},
        )
    result_ref = str(body.worker_result.get("results_ref") or "")
    task = queue.complete(session, task.id, body.worker_id, result_ref=result_ref or None)
    return task.state


def submit_failure(session: Session, queue: TaskQueue, task_id: str, body: FailureSubmit) -> str:
    task = _owned_task(session, task_id, body.worker_id)
    if body.kind == "timed_out":
        task = queue.mark_timed_out(session, task.id, body.worker_id, error_code=body.error_code)
    else:
        try:
            error_class = ErrorClass(body.error_class)
        except ValueError as exc:
            raise Problem(422, "validation_failed", "Unknown error_class.") from exc
        task = queue.fail(
            session,
            task.id,
            body.worker_id,
            retryable=body.retryable,
            error_code=body.error_code,
            error_class=error_class,
        )
    if body.message:
        _emit(
            session,
            task,
            "task.failed",
            {"error_code": body.error_code, "message": body.message[:500]},
        )
    return task.state
