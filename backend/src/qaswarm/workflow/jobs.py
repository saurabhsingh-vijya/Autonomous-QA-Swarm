"""Job state transitions. Every change goes through the state machine and writes an audit event."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from qaswarm.audit.chain import append_event
from qaswarm.db.models import Job, OutboxEvent
from qaswarm.domain.enums import JobState
from qaswarm.domain.ids import new_id
from qaswarm.domain.state_machines import JobEvent, JobStateMachine


def transition_job(
    session: Session,
    job: Job,
    event: JobEvent,
    *,
    actor_type: str,
    actor_id: str,
    actor_role: str | None = None,
    correlation_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> JobState:
    previous = JobState(job.state)
    new_state = JobStateMachine.transition(previous, event)
    now = datetime.now(UTC)
    job.state = new_state.value
    job.state_changed_at = now
    job.version += 1
    if JobStateMachine.is_terminal(new_state):
        job.ended_at = now
    info = {"from": previous.value, "to": new_state.value, "event": event.value, **(details or {})}
    session.add(
        OutboxEvent(
            id=new_id("outbox_event"),
            org_id=job.org_id,
            job_id=job.id,
            event_type="job.state_changed",
            payload={
                "job_id": job.id,
                "display_id": job.display_id,
                "from": previous.value,
                "to": new_state.value,
                "at": now.isoformat().replace("+00:00", "Z"),
                "held_reason": job.held_reason,
            },
        )
    )
    append_event(
        session,
        org_id=job.org_id,
        actor_type=actor_type,
        actor_id=actor_id,
        actor_role=actor_role,
        action="job.state_changed",
        subject_type="job",
        subject_id=job.id,
        job_id=job.id,
        correlation_id=correlation_id,
        details=info,
    )
    session.flush()
    return new_state
