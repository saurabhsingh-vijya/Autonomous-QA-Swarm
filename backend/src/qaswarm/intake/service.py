"""Intake & Pinning (stage 1): ``validating`` → ``queued`` with an immutable commit SHA."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from qaswarm.audit.chain import append_event
from qaswarm.db.models import Job, OutboxEvent, Repository
from qaswarm.domain.enums import RepositoryValidationStatus
from qaswarm.domain.ids import new_id
from qaswarm.domain.state_machines import JobEvent
from qaswarm.intake.resolvers import IntakeError, RefResolver
from qaswarm.workflow.jobs import transition_job

log = logging.getLogger("qaswarm.intake")


def _emit(session: Session, job: Job, event_type: str, payload: dict[str, Any]) -> None:
    session.add(
        OutboxEvent(
            id=new_id("outbox_event"),
            org_id=job.org_id,
            job_id=job.id,
            event_type=event_type,
            payload={"job_id": job.id, **payload},
        )
    )


def run_intake(
    session: Session, job: Job, resolver: RefResolver, *, allow_unpinned: bool = False
) -> None:
    """Pin the job's ref. On success the job is ``queued``; on failure ``failed`` or ``blocked``.

    With ``allow_unpinned`` a non-policy intake failure does not fail the job: it is queued
    without a commit (the job carries supplied inputs that agents can work on) and the
    reason is recorded as a job warning and an audit event. Policy denials always block.
    """
    repo = session.execute(
        select(Repository).where(Repository.id == job.repository_id)
    ).scalar_one()
    try:
        resolved = resolver.resolve(repo.url, job.ref)
    except IntakeError as exc:
        job.held_reason = None
        job.current_stage = "intake_and_pinning"
        repo.validation_status = RepositoryValidationStatus.VALIDATION_FAILED.value
        repo.validation_note = f"{exc.code} {exc.reason}: {exc.detail}"
        if allow_unpinned and not exc.policy:
            note = (
                f"Repository could not be pinned ({exc.code} {exc.reason}); repository checks "
                "were not planned and only the supplied inputs were used."
            )
            items = list((job.warnings or {}).get("items", []))
            job.warnings = {**(job.warnings or {}), "items": [*items, note]}
            append_event(
                session,
                org_id=job.org_id,
                actor_type="service",
                actor_id="source_intake",
                action="source.unpinned",
                subject_type="job",
                subject_id=job.id,
                job_id=job.id,
                details={"error_code": exc.code, "reason": exc.reason, "detail": exc.detail},
            )
            transition_job(
                session,
                job,
                JobEvent.VALIDATION_PASSED,
                actor_type="service",
                actor_id="source_intake",
                details={"commit_sha": None, "unpinned": exc.code},
            )
            _emit(session, job, "job.unpinned", {"error_code": exc.code, "reason": exc.reason})
            log.warning("intake failed; continuing unpinned", extra={"job_id": job.id})
            return
        event = JobEvent.POLICY_DENIED if exc.policy else JobEvent.INTAKE_ERROR
        transition_job(
            session,
            job,
            event,
            actor_type="service",
            actor_id="source_intake",
            details={"error_code": exc.code, "reason": exc.reason, "detail": exc.detail},
        )
        _emit(session, job, "job.intake_failed", {"error_code": exc.code, "reason": exc.reason})
        log.warning("intake failed", extra={"job_id": job.id, "error_code": exc.code})
        return

    now = datetime.now(UTC)
    job.commit_sha = resolved.commit_sha
    job.held_reason = None
    job.current_stage = "intake_and_pinning"
    repo.last_pinned_sha = resolved.commit_sha
    repo.validation_status = RepositoryValidationStatus.VALID.value
    repo.validation_note = f"Ref resolved by {resolved.resolver} at {now.isoformat()}"
    if resolved.default_branch and not repo.default_branch:
        repo.default_branch = resolved.default_branch
    append_event(
        session,
        org_id=job.org_id,
        actor_type="service",
        actor_id="source_intake",
        action="source.pinned",
        subject_type="job",
        subject_id=job.id,
        job_id=job.id,
        details={"ref": job.ref, "commit_sha": resolved.commit_sha, "resolver": resolved.resolver},
    )
    transition_job(
        session,
        job,
        JobEvent.VALIDATION_PASSED,
        actor_type="service",
        actor_id="source_intake",
        details={"commit_sha": resolved.commit_sha},
    )
    _emit(session, job, "job.pinned", {"ref": job.ref, "commit_sha": resolved.commit_sha})
