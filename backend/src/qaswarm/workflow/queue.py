"""PostgreSQL-backed task queue (AD-02).

Every operation runs inside the caller's session/transaction so the state change, the
TaskAttempt row, the outbox event and the audit event commit together.
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from qaswarm.audit.chain import append_event
from qaswarm.config import Settings, get_settings
from qaswarm.db.models import OutboxEvent, Task, TaskAttempt
from qaswarm.domain.enums import (
    TERMINAL_TASK_STATES,
    ErrorClass,
    RetryClass,
    TaskAttemptOutcome,
    TaskState,
)
from qaswarm.domain.ids import new_id
from qaswarm.domain.state_machines import TaskEvent, TaskStateMachine


class LeaseLost(Exception):
    """E-QUEUE-002: the caller no longer holds the lease for this task."""


@dataclass(frozen=True)
class TaskSpec:
    org_id: str
    job_id: str
    stage: str
    task_type: str
    inputs: dict[str, Any] = field(default_factory=dict)
    agent_id: str | None = None
    depends_on: list[str] = field(default_factory=list)
    soft_depends_on: list[str] = field(default_factory=list)
    priority: int = 0

    def idempotency_key(self) -> str:
        canonical = json.dumps(self.inputs, sort_keys=True, separators=(",", ":"))
        input_hash = hashlib.sha256(canonical.encode()).hexdigest()
        raw = "|".join([self.job_id, self.stage, self.task_type, input_hash])
        return hashlib.sha256(raw.encode()).hexdigest()


@dataclass(frozen=True)
class Lease:
    task_id: str
    attempt_id: str
    attempt_no: int
    lease_owner: str
    lease_expires_at: datetime


def _now() -> datetime:
    return datetime.now(UTC)


def _emit(
    session: Session, task: Task, event_type: str, extra: dict[str, Any] | None = None
) -> None:
    payload = {
        "job_id": task.job_id,
        "task_id": task.id,
        "task_type": task.task_type,
        "state": task.state,
    }
    if extra:
        payload.update(extra)
    session.add(
        OutboxEvent(
            id=new_id("outbox_event"),
            org_id=task.org_id,
            job_id=task.job_id,
            event_type=event_type,
            payload=payload,
        )
    )


def _set_state(
    session: Session,
    task: Task,
    event: TaskEvent,
    *,
    actor: str,
    details: dict[str, Any] | None = None,
) -> None:
    previous = TaskState(task.state)
    task.state = TaskStateMachine.transition(previous, event).value
    task.state_changed_at = _now()
    info = {"from": previous.value, "to": task.state, "event": event.value, **(details or {})}
    _emit(session, task, "task.state_changed", info)
    append_event(
        session,
        org_id=task.org_id,
        actor_type="service",
        actor_id=actor,
        action="task.state_changed",
        subject_type="task",
        subject_id=task.id,
        job_id=task.job_id,
        details=info,
    )


class TaskQueue:
    def __init__(self, settings: Settings | None = None, rng: random.Random | None = None) -> None:
        self.settings = settings or get_settings()
        self._rng = rng or random.Random()  # noqa: S311 - jitter only, not security

    # -- enqueue -------------------------------------------------------------------------
    def enqueue(self, session: Session, spec: TaskSpec) -> Task:
        """Insert a ``pending`` task; duplicate idempotency keys return the existing task."""
        key = spec.idempotency_key()
        stmt = (
            pg_insert(Task)
            .values(
                id=new_id("task"),
                org_id=spec.org_id,
                job_id=spec.job_id,
                stage=spec.stage,
                task_type=spec.task_type,
                agent_id=spec.agent_id,
                state=TaskState.PENDING.value,
                idempotency_key=key,
                depends_on={"tasks": spec.depends_on, "soft": spec.soft_depends_on},
                inputs=spec.inputs,
                priority=spec.priority,
                available_at=_now(),
                attempt_count=0,
                retry_class=RetryClass.TRANSIENT.value,
                created_at=_now(),
                updated_at=_now(),
                state_changed_at=_now(),
            )
            .on_conflict_do_nothing(index_elements=["idempotency_key"])
            .returning(Task.id)
        )
        inserted = session.execute(stmt).scalar_one_or_none()
        task = session.execute(select(Task).where(Task.idempotency_key == key)).scalar_one()
        if inserted is not None:
            _emit(session, task, "task.enqueued")
            append_event(
                session,
                org_id=task.org_id,
                actor_type="service",
                actor_id="workflow",
                action="task.enqueued",
                subject_type="task",
                subject_id=task.id,
                job_id=task.job_id,
                details={"task_type": task.task_type},
            )
        return task

    # -- lease ---------------------------------------------------------------------------
    def lease(
        self, session: Session, worker_id: str, task_types: list[str], batch_size: int = 1
    ) -> list[Lease]:
        now = _now()
        eligible = (
            Task.state.in_([TaskState.PENDING.value, TaskState.RETRY_SCHEDULED.value]),
            Task.task_type.in_(task_types),
            Task.available_at <= now,
        )
        # Phase 1 (no locks): find runnable candidates, skipping tasks whose dependencies are not
        # satisfied, so blocked tasks never hide runnable ones and no rows are locked needlessly.
        scan = (
            select(Task)
            .where(*eligible)
            .order_by(Task.priority.desc(), Task.available_at, Task.id)
            .limit(max(batch_size * 8, 64))
        )
        runnable = [
            t.id
            for t in session.execute(scan).scalars()
            if self._dependencies_satisfied(session, t)
        ][: max(batch_size * 8, 32)]
        if not runnable:
            return []
        # Phase 2: lock only runnable rows; concurrent leasers skip rows already locked.
        candidates = (
            select(Task)
            .where(Task.id.in_(runnable), *eligible)
            .order_by(Task.priority.desc(), Task.available_at, Task.id)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        leases: list[Lease] = []
        for task in session.execute(candidates).scalars():
            if len(leases) >= batch_size:
                break
            attempt_no = task.attempt_count + 1
            expires = now + timedelta(seconds=self.settings.lease_ttl_seconds)
            attempt = TaskAttempt(
                id=new_id("task_attempt"),
                org_id=task.org_id,
                task_id=task.id,
                attempt_no=attempt_no,
                lease_owner=worker_id,
                lease_expires_at=expires,
                last_heartbeat_at=now,
                outcome=TaskAttemptOutcome.LEASED.value,
                started_at=now,
            )
            session.add(attempt)
            task.attempt_count = attempt_no
            task.lease_owner = worker_id
            task.lease_expires_at = expires
            _set_state(
                session, task, TaskEvent.LEASED, actor=worker_id, details={"attempt_no": attempt_no}
            )
            session.flush()
            leases.append(Lease(task.id, attempt.id, attempt_no, worker_id, expires))
        return leases

    def _dependencies_satisfied(self, session: Session, task: Task) -> bool:
        """Hard dependencies must be ``succeeded``; soft dependencies must be terminal."""
        hard: list[str] = list(task.depends_on.get("tasks", []))
        soft: list[str] = list(task.depends_on.get("soft", []))
        if not hard and not soft:
            return True
        rows = session.execute(select(Task.id, Task.state).where(Task.id.in_(hard + soft))).all()
        states = {tid: st for tid, st in rows}
        if any(states.get(t) != TaskState.SUCCEEDED.value for t in hard):
            return False
        terminal = {s.value for s in TERMINAL_TASK_STATES}
        return all(states.get(t) in terminal for t in soft)

    # -- heartbeat -----------------------------------------------------------------------
    def heartbeat(self, session: Session, task_id: str, worker_id: str) -> datetime:
        now = _now()
        expires = now + timedelta(seconds=self.settings.lease_ttl_seconds)
        task = session.execute(
            select(Task).where(Task.id == task_id).with_for_update()
        ).scalar_one_or_none()
        if (
            task is None
            or task.lease_owner != worker_id
            or task.state not in (TaskState.LEASED.value, TaskState.RUNNING.value)
            or (task.lease_expires_at and task.lease_expires_at < now)
        ):
            raise LeaseLost(task_id)
        task.lease_expires_at = expires
        session.execute(
            update(TaskAttempt)
            .where(TaskAttempt.task_id == task_id, TaskAttempt.attempt_no == task.attempt_count)
            .values(
                lease_expires_at=expires,
                last_heartbeat_at=now,
                outcome=TaskAttemptOutcome.RUNNING.value,
            )
        )
        if task.state == TaskState.LEASED.value:
            _set_state(session, task, TaskEvent.FIRST_HEARTBEAT, actor=worker_id)
        return expires

    # -- completion ----------------------------------------------------------------------
    def _owned_running_task(self, session: Session, task_id: str, worker_id: str) -> Task:
        task = session.execute(
            select(Task).where(Task.id == task_id).with_for_update()
        ).scalar_one_or_none()
        if (
            task is None
            or task.lease_owner != worker_id
            or task.state not in (TaskState.LEASED.value, TaskState.RUNNING.value)
        ):
            raise LeaseLost(task_id)
        if task.state == TaskState.LEASED.value:
            _set_state(session, task, TaskEvent.FIRST_HEARTBEAT, actor=worker_id)
        return task

    def complete(
        self, session: Session, task_id: str, worker_id: str, result_ref: str | None = None
    ) -> Task:
        task = self._owned_running_task(session, task_id, worker_id)
        self._close_attempt(session, task, TaskAttemptOutcome.SUCCEEDED, None, None)
        task.lease_owner = None
        task.lease_expires_at = None
        _set_state(
            session,
            task,
            TaskEvent.VALID_RESULT,
            actor=worker_id,
            details={"result_ref": result_ref},
        )
        return task

    def fail(
        self,
        session: Session,
        task_id: str,
        worker_id: str,
        *,
        retryable: bool,
        error_code: str,
        error_class: ErrorClass = ErrorClass.INFRASTRUCTURE_ERROR,
    ) -> Task:
        task = self._owned_running_task(session, task_id, worker_id)
        self._close_attempt(session, task, TaskAttemptOutcome.FAILED, error_code, error_class.value)
        task.last_error_code = error_code
        task.last_error_class = error_class.value
        task.lease_owner = None
        task.lease_expires_at = None
        if retryable:
            _set_state(
                session,
                task,
                TaskEvent.TRANSIENT_ERROR,
                actor=worker_id,
                details={"error_code": error_code},
            )
            self._schedule_retry_or_fail(session, task, actor=worker_id)
        else:
            _set_state(
                session,
                task,
                TaskEvent.NON_RETRYABLE_ERROR,
                actor=worker_id,
                details={"error_code": error_code},
            )
        return task

    def _close_attempt(
        self,
        session: Session,
        task: Task,
        outcome: TaskAttemptOutcome,
        error_code: str | None,
        error_class: str | None,
    ) -> None:
        session.execute(
            update(TaskAttempt)
            .where(TaskAttempt.task_id == task.id, TaskAttempt.attempt_no == task.attempt_count)
            .values(
                outcome=outcome.value,
                ended_at=_now(),
                error_code=error_code,
                error_class=error_class,
            )
        )

    # -- backoff -------------------------------------------------------------------------
    def backoff_seconds(self, attempt_count: int) -> float:
        base = self.settings.backoff_seconds[
            min(attempt_count, len(self.settings.backoff_seconds)) - 1
        ]
        jitter = self.settings.backoff_jitter
        return base * self._rng.uniform(1 - jitter, 1 + jitter)

    def _schedule_retry_or_fail(self, session: Session, task: Task, *, actor: str) -> None:
        if task.attempt_count > self.settings.task_max_retries:
            _set_state(
                session,
                task,
                TaskEvent.BUDGET_EXHAUSTED,
                actor=actor,
                details={"attempt_count": task.attempt_count},
            )
            return
        delay = self.backoff_seconds(task.attempt_count)
        task.available_at = _now() + timedelta(seconds=delay)
        _set_state(
            session,
            task,
            TaskEvent.BUDGET_REMAINS,
            actor=actor,
            details={"attempt_count": task.attempt_count, "backoff_seconds": round(delay, 2)},
        )
        _emit(
            session, task, "task.retry_scheduled", {"available_at": task.available_at.isoformat()}
        )

    # -- reaper --------------------------------------------------------------------------
    def reap_expired_leases(self, session: Session) -> list[str]:
        now = _now()
        expired = (
            session.execute(
                select(Task)
                .where(
                    Task.state.in_([TaskState.LEASED.value, TaskState.RUNNING.value]),
                    Task.lease_expires_at < now,
                )
                .with_for_update(skip_locked=True)
            )
            .scalars()
            .all()
        )
        reaped: list[str] = []
        for task in expired:
            self._close_attempt(
                session,
                task,
                TaskAttemptOutcome.LEASE_EXPIRED,
                "E-QUEUE-001",
                ErrorClass.INFRASTRUCTURE_ERROR.value,
            )
            task.last_error_code = "E-QUEUE-001"
            task.last_error_class = ErrorClass.INFRASTRUCTURE_ERROR.value
            task.lease_owner = None
            task.lease_expires_at = None
            _set_state(
                session,
                task,
                TaskEvent.LEASE_EXPIRED,
                actor="reaper",
                details={"error_code": "E-QUEUE-001"},
            )
            self._schedule_retry_or_fail(session, task, actor="reaper")
            reaped.append(task.id)
        return reaped

    def cancel_job_tasks(self, session: Session, job_id: str, actor: str) -> int:
        tasks = (
            session.execute(
                select(Task)
                .where(
                    Task.job_id == job_id,
                    Task.state.in_(
                        [
                            TaskState.PENDING.value,
                            TaskState.LEASED.value,
                            TaskState.RUNNING.value,
                            TaskState.RETRY_SCHEDULED.value,
                        ]
                    ),
                )
                .with_for_update()
            )
            .scalars()
            .all()
        )
        for task in tasks:
            task.lease_owner = None
            task.lease_expires_at = None
            _set_state(session, task, TaskEvent.JOB_CANCELLING, actor=actor)
        return len(tasks)
