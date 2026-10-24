"""Scheduler role: drives jobs through the lifecycle (phase 2).

Each ``tick`` runs these steps, every step in its own transaction:

1. ``admit``      ``validating`` jobs → Intake & Pinning (ref → SHA) → ``queued`` / ``failed`` / ``blocked``
2. ``plan``       ``queued`` → ``planning`` → template task DAG enqueued → ``running``
3. ``reap``       expired leases → ``failed_retryable`` → retry or ``failed``
4. ``expire``     tasks past the task wall clock → ``timed_out``
5. ``propagate``  pending tasks whose dependency did not succeed → ``skipped``
6. ``advance``    ``running`` → ``analyzing`` → ``reporting`` → ``completed[_with_warnings]`` / ``failed``
7. ``deadlines``  jobs past their wall clock → ``cancelling`` (reason timeout)
8. ``confirm``    ``cancelling`` jobs whose workers are all destroyed → ``cancelled`` / ``timed_out``

Run it as ``python -m qaswarm.workflow.scheduler`` or embedded in the API process
(``AQS_EMBEDDED_SCHEDULER=true``, local development only).
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from qaswarm.config import Settings, get_settings
from qaswarm.db.models import Job, Repository, Task, WorkerRun
from qaswarm.db.session import session_scope
from qaswarm.domain.enums import PIPELINE_STAGES, TERMINAL_TASK_STATES, JobState, TaskState
from qaswarm.domain.state_machines import JobEvent
from qaswarm.intake import RefResolver, resolver_for, run_intake
from qaswarm.intake.resolvers import IntakeError
from qaswarm.reporting.basic import build_report
from qaswarm.workflow.jobs import transition_job
from qaswarm.workflow.orchestrator import Orchestrator
from qaswarm.workflow.queue import TaskQueue

log = logging.getLogger("qaswarm.scheduler")

_FAILED_TASK_STATES = {
    TaskState.FAILED.value,
    TaskState.TIMED_OUT.value,
    TaskState.INVALID_OUTPUT.value,
}
_WARNING_TASK_STATES = _FAILED_TASK_STATES | {TaskState.SKIPPED.value, TaskState.CANCELLED.value}

ResolverFactory = Callable[[str], RefResolver]


class _FailingResolver:
    """Resolver stand-in that re-raises the factory's intake error inside ``run_intake``."""

    name = "failed-intake"

    def __init__(self, error: IntakeError) -> None:
        self._error = error

    def resolve(self, url: str, ref: str) -> Any:
        raise self._error


@dataclass
class TickSummary:
    admitted: int = 0
    planned: int = 0
    reaped: int = 0
    expired: int = 0
    skipped: int = 0
    advanced: int = 0
    deadlines: int = 0
    confirmed: int = 0
    errors: list[str] = field(default_factory=list)


def _now() -> datetime:
    return datetime.now(UTC)


class Scheduler:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        queue: TaskQueue | None = None,
        resolver_factory: ResolverFactory | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.queue = queue or TaskQueue(self.settings)
        self._resolver_factory = resolver_factory or self._default_resolver
        self.orchestrator = Orchestrator.from_settings(self.settings)
        self.orchestrator.queue = self.queue

    def _default_resolver(self, url: str) -> RefResolver:
        s = self.settings
        return resolver_for(
            url,
            dev_fixture_repos=s.dev_fixture_repos,
            fixtures_dir=s.fixtures_dir,
            timeout_seconds=s.intake_timeout_seconds,
            dns_check=s.intake_dns_check,
        )

    # ---------------------------------------------------------------- tick
    def tick(self) -> TickSummary:
        summary = TickSummary()
        steps: list[tuple[str, Callable[[TickSummary], None]]] = [
            ("admit", self.admit),
            ("plan", self.plan),
            ("reap", self.reap),
            ("expire", self.expire),
            ("propagate", self.propagate),
            ("advance", self.advance),
            ("deadlines", self.deadlines),
            ("confirm", self.confirm),
        ]
        for name, step in steps:
            try:
                step(summary)
            except Exception as exc:  # one failing step must not stop the others
                log.exception("scheduler step failed", extra={"step": name})
                summary.errors.append(f"{name}: {type(exc).__name__}")
        return summary

    def run_forever(self, stop: threading.Event | None = None) -> None:
        stop = stop or threading.Event()
        log.info("scheduler started", extra={"interval": self.settings.scheduler_interval_seconds})
        while not stop.is_set():
            self.tick()
            stop.wait(self.settings.scheduler_interval_seconds)

    # ------------------------------------------------------------- 1 admit
    def admit(self, summary: TickSummary) -> None:
        with session_scope() as s:
            ids = (
                s.execute(
                    select(Job.id)
                    .where(Job.state == JobState.VALIDATING.value)
                    .order_by(Job.created_at)
                )
                .scalars()
                .all()
            )
        for job_id in ids:
            with session_scope() as s:
                job = s.execute(
                    select(Job).where(Job.id == job_id).with_for_update(skip_locked=True)
                ).scalar_one_or_none()
                if job is None or job.state != JobState.VALIDATING.value:
                    continue
                repo = s.execute(
                    select(Repository).where(Repository.id == job.repository_id)
                ).scalar_one()
                inputs = job.inputs or {}
                has_inputs = bool(inputs.get("requirements")) or bool(inputs.get("api_checks"))
                try:
                    resolver = self._resolver_factory(repo.url)
                except IntakeError as exc:
                    if has_inputs and not exc.policy:
                        run_intake(s, job, _FailingResolver(exc), allow_unpinned=True)
                        summary.admitted += 1
                        continue
                    job.held_reason = None
                    transition_job(
                        s,
                        job,
                        JobEvent.POLICY_DENIED if exc.policy else JobEvent.INTAKE_ERROR,
                        actor_type="service",
                        actor_id="source_intake",
                        details={"error_code": exc.code, "reason": exc.reason},
                    )
                    summary.admitted += 1
                    continue
                run_intake(s, job, resolver, allow_unpinned=has_inputs)
                summary.admitted += 1

    # -------------------------------------------------------------- 2 plan
    def plan(self, summary: TickSummary) -> None:
        with session_scope() as s:
            ids = (
                s.execute(
                    select(Job.id)
                    .where(Job.state == JobState.QUEUED.value)
                    .order_by(Job.created_at)
                )
                .scalars()
                .all()
            )
        for job_id in ids:
            with session_scope() as s:
                job = s.execute(
                    select(Job).where(Job.id == job_id).with_for_update(skip_locked=True)
                ).scalar_one_or_none()
                if job is None or job.state != JobState.QUEUED.value:
                    continue
                repo = s.execute(
                    select(Repository).where(Repository.id == job.repository_id)
                ).scalar_one()
                transition_job(
                    s, job, JobEvent.PLANNER_LEASED, actor_type="service", actor_id="scheduler"
                )
                self.orchestrator.plan_job(s, job, repository_url=repo.url, provider=repo.provider)
                summary.planned += 1

    # ----------------------------------------------------- 3/4/5 maintenance
    def reap(self, summary: TickSummary) -> None:
        with session_scope() as s:
            summary.reaped += len(self.queue.reap_expired_leases(s))

    def expire(self, summary: TickSummary) -> None:
        with session_scope() as s:
            summary.expired += len(
                self.queue.expire_running_tasks(s, self.settings.task_wall_clock_seconds)
            )

    def propagate(self, summary: TickSummary) -> None:
        with session_scope() as s:
            job_ids = (
                s.execute(
                    select(Task.job_id)
                    .where(Task.state == TaskState.PENDING.value)
                    .group_by(Task.job_id)
                )
                .scalars()
                .all()
            )
        for job_id in job_ids:
            with session_scope() as s:
                summary.skipped += len(
                    self.queue.skip_blocked_dependents(s, job_id, actor="scheduler")
                )

    # ----------------------------------------------------------- 6 advance
    @staticmethod
    def current_stage(tasks: list[Task]) -> str | None:
        order = {stage: i for i, stage in enumerate(PIPELINE_STAGES)}
        open_stages = sorted(
            (order.get(t.stage, 99), t.stage) for t in tasks if t.state not in TERMINAL_TASK_STATES
        )
        if open_stages:
            return open_stages[0][1]
        return None

    def advance(self, summary: TickSummary) -> None:
        active = [JobState.RUNNING.value, JobState.ANALYZING.value, JobState.REPORTING.value]
        with session_scope() as s:
            ids = s.execute(select(Job.id).where(Job.state.in_(active))).scalars().all()
        for job_id in ids:
            with session_scope() as s:
                job = s.execute(
                    select(Job).where(Job.id == job_id).with_for_update(skip_locked=True)
                ).scalar_one_or_none()
                if job is None or job.state not in active:
                    continue
                if self._advance_one(s, job):
                    summary.advanced += 1

    def _advance_one(self, s: Session, job: Job) -> bool:
        """Job state follows the tasks: the orchestrator's ``reconcile`` owns the transitions
        (critical-path failure with a partial report, testing → analyzing → reporting →
        completed). This step also keeps ``current_stage`` honest while tasks are open."""
        before = (job.state, job.current_stage, job.version)
        tasks = list(s.execute(select(Task).where(Task.job_id == job.id)).scalars())
        if job.state == JobState.RUNNING.value:
            stage = self.current_stage(tasks)
            if stage is not None and job.current_stage != stage:
                job.current_stage = stage
        self.orchestrator.reconcile(s, job)
        s.refresh(job)
        return (job.state, job.current_stage, job.version) != before

    # --------------------------------------------------------- 7 deadlines
    def deadlines(self, summary: TickSummary) -> None:
        now = _now()
        terminal_or_cancelling = [
            s.value
            for s in JobState
            if s
            in {
                JobState.COMPLETED,
                JobState.COMPLETED_WITH_WARNINGS,
                JobState.FAILED,
                JobState.CANCELLED,
                JobState.TIMED_OUT,
                JobState.BLOCKED,
                JobState.CANCELLING,
            }
        ]
        with session_scope() as s:
            ids = (
                s.execute(
                    select(Job.id).where(
                        Job.deadline_at < now, Job.state.not_in(terminal_or_cancelling)
                    )
                )
                .scalars()
                .all()
            )
        for job_id in ids:
            with session_scope() as s:
                job = s.execute(
                    select(Job).where(Job.id == job_id).with_for_update(skip_locked=True)
                ).scalar_one_or_none()
                if job is None or job.state in terminal_or_cancelling:
                    continue
                job.cancel_reason = "job wall-clock limit exceeded"
                job.held_reason = None
                transition_job(
                    s,
                    job,
                    JobEvent.DEADLINE_PASSED,
                    actor_type="service",
                    actor_id="scheduler",
                    details={
                        "deadline_at": job.deadline_at.isoformat() if job.deadline_at else None
                    },
                )
                self.queue.cancel_job_tasks(s, job.id, actor="scheduler")
                summary.deadlines += 1

    # ----------------------------------------------------------- 8 confirm
    def confirm(self, summary: TickSummary) -> None:
        with session_scope() as s:
            ids = (
                s.execute(select(Job.id).where(Job.state == JobState.CANCELLING.value))
                .scalars()
                .all()
            )
        for job_id in ids:
            with session_scope() as s:
                job = s.execute(
                    select(Job).where(Job.id == job_id).with_for_update(skip_locked=True)
                ).scalar_one_or_none()
                if job is None or job.state != JobState.CANCELLING.value:
                    continue
                alive = s.execute(
                    select(func.count())
                    .select_from(WorkerRun)
                    .where(WorkerRun.job_id == job.id, WorkerRun.destroyed_at.is_(None))
                ).scalar_one()
                open_tasks = s.execute(
                    select(func.count())
                    .select_from(Task)
                    .where(
                        Task.job_id == job.id,
                        Task.state.not_in([t.value for t in TERMINAL_TASK_STATES]),
                    )
                ).scalar_one()
                if alive or open_tasks:
                    continue
                by_timeout = job.cancel_requested_at is None
                build_report(s, job, partial=True)
                transition_job(
                    s,
                    job,
                    JobEvent.CLEANUP_CONFIRMED_TIMEOUT
                    if by_timeout
                    else JobEvent.CLEANUP_CONFIRMED_USER,
                    actor_type="service",
                    actor_id="scheduler",
                    details={"workers_alive": 0},
                )
                summary.confirmed += 1


def main() -> None:  # pragma: no cover - process entry point
    from qaswarm.telemetry.logging import configure_logging

    settings = get_settings()
    configure_logging(settings.log_level)
    Scheduler(settings).run_forever()


if __name__ == "__main__":  # pragma: no cover
    main()


def run_until_idle(scheduler: Scheduler, *, max_ticks: int = 50, sleep: float = 0.0) -> int:
    """Test helper: tick until a tick changes nothing (or ``max_ticks``). Returns ticks run."""
    for i in range(1, max_ticks + 1):
        summary = scheduler.tick()
        changed = any(
            getattr(summary, f)
            for f in (
                "admitted",
                "planned",
                "reaped",
                "expired",
                "skipped",
                "advanced",
                "deadlines",
                "confirmed",
            )
        )
        if not changed:
            return i
        if sleep:
            time.sleep(sleep)
    return max_ticks
