"""Job creation (idempotent, duplicate-safe), listing, cancel and the SSE event source.

Jobs are created ``created`` → ``validating`` and held there: source intake arrives in slice 1b.
Nothing is executed and no later state is fabricated.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from qaswarm.api.auth import Principal
from qaswarm.api.errors import Problem
from qaswarm.api.pagination import encode_cursor
from qaswarm.api.schemas import (
    JobCancelOut,
    JobCreate,
    JobDetailOut,
    JobLinks,
    JobOut,
    StageProgress,
)
from qaswarm.api.services.repositories import get_repository_row
from qaswarm.audit.chain import append_event
from qaswarm.config import Settings
from qaswarm.db.models import (
    IdempotencyRecord,
    Job,
    JobPlan,
    Organization,
    OutboxEvent,
    Report,
    Task,
)
from qaswarm.db.session import session_factory
from qaswarm.domain.enums import PIPELINE_STAGES, TERMINAL_JOB_STATES, JobState, Role
from qaswarm.domain.ids import display_id, new_id
from qaswarm.domain.state_machines import JobEvent, JobStateMachine
from qaswarm.workflow.jobs import transition_job
from qaswarm.workflow.orchestrator import Orchestrator
from qaswarm.workflow.queue import TaskQueue

HELD_REASON = "intake arrives in slice 1b"
JOBS_ENDPOINT = "POST /api/v1/jobs"


def profile_hash(profiles: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(profiles, sort_keys=True).encode()).hexdigest()


def _links(job: Job) -> JobLinks:
    return JobLinks(self=f"/api/v1/jobs/{job.id}", events=f"/api/v1/jobs/{job.id}/events")


def _columns(job: Job) -> dict[str, Any]:
    return {attr.key: getattr(job, attr.key) for attr in inspect(Job).mapper.column_attrs}


def to_out(job: Job) -> JobOut:
    return JobOut.model_validate({**_columns(job), "links": _links(job)})


_STAGE_RANK = {
    "failed": 5,
    "running": 4,
    "leased": 4,
    "pending": 3,
    "retry_scheduled": 3,
    "skipped": 2,
    "cancelled": 2,
    "succeeded": 1,
}


def _stages(job: Job, tasks: list[Task]) -> list[StageProgress]:
    """Derive stage status from real task states; stages with no tasks are honest about why."""
    by_stage: dict[str, list[Task]] = {}
    for t in tasks:
        by_stage.setdefault(t.stage, []).append(t)
    terminal = job.state in TERMINAL_JOB_STATES
    stages: list[StageProgress] = []
    for stage in PIPELINE_STAGES:
        status, note = "pending", None
        if stage == "intake_and_pinning":
            if job.state == JobState.VALIDATING.value and job.held_reason:
                status, note = "held", job.held_reason
            elif job.state == JobState.VALIDATING.value:
                status = "running"
            elif job.state == JobState.AWAITING_APPROVAL.value:
                status, note = "awaiting_approval", job.held_reason
            else:
                status, note = (
                    "not_run",
                    "Repository intake arrives in slice 1b; this job used supplied inputs.",
                )
        elif stage in by_stage:
            states = [t.state for t in by_stage[stage]]
            if any(s in ("failed", "invalid_output", "timed_out") for s in states):
                status = "failed"
            elif any(s in ("leased", "running") for s in states):
                status = "running"
            elif all(s == "succeeded" for s in states):
                status = "succeeded"
            elif all(s in ("succeeded", "skipped") for s in states):
                status, note = "succeeded", "some tasks skipped"
            elif any(s == "cancelled" for s in states):
                status = "cancelled"
            else:
                status = "pending"
            agents = sorted({t.agent_id for t in by_stage[stage] if t.agent_id})
            note = note or ("agents " + ", ".join(agents) if agents else None)
        elif stage == "cleanup_and_retention":
            status = "succeeded" if terminal and tasks else ("not_run" if terminal else "pending")
            note = "no workers to destroy in this build" if terminal and tasks else None
        elif terminal or tasks:
            status, note = (
                "not_planned",
                "not part of this job's plan (no engine for this stage yet)",
            )
        stages.append(StageProgress(stage=stage, status=status, note=note))
    return stages


def to_detail(session: Session, job: Job) -> JobDetailOut:
    tasks = list(
        session.execute(
            select(Task).where(Task.job_id == job.id).order_by(Task.created_at)
        ).scalars()
    )
    counts: dict[str, int] = {}
    for t in tasks:
        counts[t.state] = counts.get(t.state, 0) + 1
    report_available = (
        session.execute(
            select(func.count()).select_from(Report).where(Report.job_id == job.id)
        ).scalar_one()
        > 0
    )
    plan_available = (
        session.execute(
            select(func.count()).select_from(JobPlan).where(JobPlan.job_id == job.id)
        ).scalar_one()
        > 0
    )
    return JobDetailOut.model_validate(
        {
            **_columns(job),
            "links": _links(job),
            "stages": _stages(job, tasks),
            "report_available": report_available,
            "plan_available": plan_available,
            "task_summary": counts,
        }
    )


def _request_hash(body: JobCreate) -> str:
    return hashlib.sha256(body.model_dump_json().encode()).hexdigest()


def find_idempotent_replay(
    session: Session, principal: Principal, key: str, body: JobCreate
) -> IdempotencyRecord | None:
    rec = session.execute(
        select(IdempotencyRecord).where(
            IdempotencyRecord.principal_id == principal.user_id,
            IdempotencyRecord.endpoint == JOBS_ENDPOINT,
            IdempotencyRecord.idempotency_key == key,
            IdempotencyRecord.expires_at > datetime.now(UTC),
        )
    ).scalar_one_or_none()
    if rec is None:
        return None
    if rec.request_hash != _request_hash(body):
        raise Problem(
            422,
            "idempotency_key_reused",
            "This Idempotency-Key was already used with a different request body.",
        )
    return rec


def create_job(
    session: Session,
    principal: Principal,
    body: JobCreate,
    *,
    idempotency_key: str,
    settings: Settings,
    correlation_id: str | None,
) -> tuple[int, dict[str, Any]]:
    if body.force_new and principal.role is not Role.QA_LEAD:
        raise Problem(
            403,
            "insufficient_role",
            "force_new=true requires the QA Lead role.",
            required_roles=[Role.QA_LEAD.value],
        )
    repo = get_repository_row(session, principal, body.repository_id)
    profiles = body.profiles.model_dump(mode="json")
    phash = profile_hash(profiles)

    existing = session.execute(
        select(Job)
        .where(
            Job.repository_id == repo.id,
            Job.ref == body.ref,
            Job.profile_hash == phash,
            Job.state.not_in([s.value for s in TERMINAL_JOB_STATES]),
        )
        .order_by(Job.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if existing is not None and not body.force_new:
        raise Problem(
            409,
            "job_duplicate_active",
            f"{existing.display_id} is still active for the same repository, ref and profile set.",
            title="An equivalent job is already active",
            existing_job={
                "id": existing.id,
                "display_id": existing.display_id,
                "state": existing.state,
            },
            hint="Use the existing job, or ask a QA Lead to create a new one with force_new=true.",
        )

    org = session.execute(
        select(Organization).where(Organization.id == principal.org_id).with_for_update()
    ).scalar_one()
    org.job_sequence += 1
    now = datetime.now(UTC)
    job = Job(
        id=new_id("job"),
        org_id=principal.org_id,
        project_id=repo.project_id,
        repository_id=repo.id,
        display_id=display_id("QJ", org.job_sequence),
        ref=body.ref,
        profiles=profiles,
        profile_hash=phash,
        state=JobState.CREATED.value,
        inputs=body.inputs.model_dump(mode="json"),
        require_plan_approval=body.require_plan_approval,
        warnings={},
        force_new=body.force_new,
        created_by=principal.user_id,
        deadline_at=now + timedelta(seconds=settings.job_wall_clock_seconds),
        version=1,
    )
    session.add(job)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise Problem(
            409,
            "job_duplicate_active",
            "An equivalent job became active concurrently; retry to get its link.",
            title="An equivalent job is already active",
        ) from exc

    append_event(
        session,
        org_id=job.org_id,
        actor_type="user",
        actor_id=principal.user_id,
        actor_role=principal.role.value,
        action="job.created",
        subject_type="job",
        subject_id=job.id,
        job_id=job.id,
        correlation_id=correlation_id,
        details={
            "repository_id": repo.id,
            "ref": job.ref,
            "profiles": profiles,
            "force_new": body.force_new,
            "idempotency_key_sha256": hashlib.sha256(idempotency_key.encode()).hexdigest(),
        },
    )
    transition_job(
        session,
        job,
        JobEvent.JOB_ADMITTED,
        actor_type="service",
        actor_id="api",
        correlation_id=correlation_id,
    )
    Orchestrator.from_settings(settings).admit(
        session, job, actor_id=principal.user_id, correlation_id=correlation_id
    )
    if job.held_reason:
        append_event(
            session,
            org_id=job.org_id,
            actor_type="service",
            actor_id="workflow",
            action="job.held",
            subject_type="job",
            subject_id=job.id,
            job_id=job.id,
            correlation_id=correlation_id,
            details={"reason": job.held_reason},
        )
        session.add(
            OutboxEvent(
                id=new_id("outbox_event"),
                org_id=job.org_id,
                job_id=job.id,
                event_type="job.held",
                payload={"job_id": job.id, "reason": job.held_reason, "stage": job.current_stage},
            )
        )

    status = 202
    body_out = json.loads(to_out(job).model_dump_json())
    session.add(
        IdempotencyRecord(
            org_id=principal.org_id,
            principal_id=principal.user_id,
            endpoint=JOBS_ENDPOINT,
            idempotency_key=idempotency_key,
            request_hash=_request_hash(body),
            status_code=status,
            response_body=body_out,
            response_headers={"Location": f"/api/v1/jobs/{job.id}"},
            expires_at=now + timedelta(hours=settings.idempotency_ttl_hours),
        )
    )
    session.flush()
    return status, body_out


def get_job_row(session: Session, principal: Principal, job_id: str) -> Job:
    job = session.execute(
        select(Job).where(Job.id == job_id, Job.org_id == principal.org_id)
    ).scalar_one_or_none()
    if job is None:
        raise Problem(404, "not_found", "Job not found.")
    return job


def list_jobs(
    session: Session,
    principal: Principal,
    *,
    states: list[str] | None,
    repository_id: str | None,
    project_id: str | None,
    limit: int,
    after: str | None,
) -> tuple[list[JobOut], str | None]:
    stmt = (
        select(Job).where(Job.org_id == principal.org_id).order_by(Job.id.desc()).limit(limit + 1)
    )
    if states:
        valid = {s.value for s in JobState}
        unknown = [s for s in states if s not in valid]
        if unknown:
            raise Problem(400, "unsupported_filter", f"Unknown job state(s): {', '.join(unknown)}.")
        stmt = stmt.where(Job.state.in_(states))
    if repository_id:
        stmt = stmt.where(Job.repository_id == repository_id)
    if project_id:
        stmt = stmt.where(Job.project_id == project_id)
    if after:
        stmt = stmt.where(Job.id < after)
    rows = list(session.execute(stmt).scalars())
    next_cursor = encode_cursor(rows[limit - 1].id) if len(rows) > limit else None
    return [to_out(j) for j in rows[:limit]], next_cursor


def cancel_job(
    session: Session,
    principal: Principal,
    job_id: str,
    reason: str | None,
    if_match: int | None,
    correlation_id: str | None,
) -> JobCancelOut:
    job = session.execute(
        select(Job).where(Job.id == job_id, Job.org_id == principal.org_id).with_for_update()
    ).scalar_one_or_none()
    if job is None:
        raise Problem(404, "not_found", "Job not found.")
    if if_match is not None and if_match != job.version:
        raise Problem(412, "etag_mismatch", "The job changed since you loaded it.")
    state = JobState(job.state)
    if state is JobState.CANCELLING:
        return JobCancelOut(
            id=job.id,
            state=state,
            requested_by=job.created_by,
            requested_at=job.cancel_requested_at or job.state_changed_at,
        )
    if not JobStateMachine.can(state, JobEvent.CANCEL_REQUESTED):
        raise Problem(
            409,
            "invalid_state_transition",
            f"Job {job.display_id} is {state.value} and cannot be cancelled.",
        )
    now = datetime.now(UTC)
    job.cancel_requested_at = now
    job.cancel_reason = reason
    transition_job(
        session,
        job,
        JobEvent.CANCEL_REQUESTED,
        actor_type="user",
        actor_id=principal.user_id,
        actor_role=principal.role.value,
        correlation_id=correlation_id,
        details={"reason": reason},
    )
    cancelled_tasks = TaskQueue().cancel_job_tasks(session, job.id, actor=principal.user_id)
    # No workers exist in this slice, so cleanup is confirmed immediately. Slice 1c will wait for
    # the Execution Service to confirm worker destruction before this transition.
    job.held_reason = None
    transition_job(
        session,
        job,
        JobEvent.CLEANUP_CONFIRMED_USER,
        actor_type="service",
        actor_id="workflow",
        correlation_id=correlation_id,
        details={"cancelled_tasks": cancelled_tasks, "workers_destroyed": 0},
    )
    return JobCancelOut(
        id=job.id, state=JobState(job.state), requested_by=principal.user_id, requested_at=now
    )


# ---- SSE ----------------------------------------------------------------------------------
def _format_sse(event_id: str, event_type: str, data: dict[str, Any]) -> str:
    return f"id: {event_id}\nevent: {event_type}\ndata: {json.dumps(data, default=str)}\n\n"


def job_event_stream(
    job_id: str,
    org_id: str,
    *,
    last_event_id: str | None,
    heartbeat_seconds: int,
    poll_seconds: float = 1.0,
    max_seconds: float | None = None,
) -> Iterator[str]:
    """Yield SSE frames for a job from the outbox table; ``id`` is the outbox sequence number.

    Replays everything after ``last_event_id`` and ends with ``stream.end`` once the job is
    terminal and all events have been delivered.
    """
    try:
        cursor = int(last_event_id) if last_event_id else 0
    except ValueError:
        cursor = 0
    started = time.monotonic()
    last_sent = time.monotonic()
    factory = session_factory()
    while True:
        with factory() as session:
            rows = (
                session.execute(
                    select(OutboxEvent)
                    .where(
                        OutboxEvent.job_id == job_id,
                        OutboxEvent.org_id == org_id,
                        OutboxEvent.seq > cursor,
                    )
                    .order_by(OutboxEvent.seq)
                    .limit(200)
                )
                .scalars()
                .all()
            )
            for ev in rows:
                cursor = ev.seq
                yield _format_sse(str(ev.seq), ev.event_type, ev.payload)
                last_sent = time.monotonic()
            state = session.execute(select(Job.state).where(Job.id == job_id)).scalar_one_or_none()
        if state is None or (state in {s.value for s in TERMINAL_JOB_STATES} and not rows):
            yield _format_sse(str(cursor), "stream.end", {"job_id": job_id, "state": state})
            return
        if time.monotonic() - last_sent >= heartbeat_seconds:
            yield _format_sse(
                str(cursor),
                "heartbeat",
                {"at": datetime.now(UTC).isoformat().replace("+00:00", "Z")},
            )
            last_sent = time.monotonic()
        if max_seconds is not None and time.monotonic() - started >= max_seconds:
            return
        time.sleep(poll_seconds)
