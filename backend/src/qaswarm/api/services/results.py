"""Read side of phase 2: tasks, checks, test executions, evidence, reports, run comparison."""

from __future__ import annotations

from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from qaswarm.api.auth import Principal
from qaswarm.api.errors import Problem
from qaswarm.api.schemas import (
    AuditEventOut,
    CheckRunOut,
    CompareCheck,
    CompareJobRef,
    CompareOut,
    CompareTest,
    EvidenceContentOut,
    EvidenceItemOut,
    ReportOut,
    TaskAttemptOut,
    TaskOut,
    TestExecutionOut,
    WorkerRunOut,
)
from qaswarm.api.services.jobs import get_job_row
from qaswarm.db.models import (
    AuditEvent,
    CheckRun,
    EvidenceItem,
    Job,
    Report,
    Task,
    TaskAttempt,
    TestExecution,
    WorkerRun,
)
from qaswarm.domain.enums import CheckOutcome, JobState, TestExecutionStatus
from qaswarm.evidence import EvidenceStore
from qaswarm.evidence.store import TEXT_MEDIA_PREFIXES, EvidenceIntegrityError
from qaswarm.reporting import compose_report

_CHECK_RANK = {
    CheckOutcome.PASSED.value: 3,
    CheckOutcome.SKIPPED.value: 2,
    CheckOutcome.ERROR.value: 1,
    CheckOutcome.FAILED.value: 0,
}
_TEST_RANK = {
    TestExecutionStatus.PASSED.value: 3,
    TestExecutionStatus.SKIPPED.value: 2,
    TestExecutionStatus.BLOCKED.value: 2,
    TestExecutionStatus.INFRASTRUCTURE_ERROR.value: 1,
    TestExecutionStatus.TIMED_OUT.value: 1,
    TestExecutionStatus.FAILED.value: 0,
}


def list_tasks(session: Session, principal: Principal, job_id: str) -> list[TaskOut]:
    job = get_job_row(session, principal, job_id)
    tasks = list(
        session.execute(
            select(Task)
            .where(Task.job_id == job.id)
            .order_by(Task.priority.desc(), Task.created_at)
        ).scalars()
    )
    attempts = list(
        session.execute(
            select(TaskAttempt)
            .where(TaskAttempt.task_id.in_([t.id for t in tasks] or [""]))
            .order_by(TaskAttempt.attempt_no)
        ).scalars()
    )
    by_task: dict[str, list[TaskAttemptOut]] = {}
    for a in attempts:
        by_task.setdefault(a.task_id, []).append(TaskAttemptOut.model_validate(a))
    out: list[TaskOut] = []
    for t in tasks:
        out.append(
            TaskOut(
                id=t.id,
                job_id=t.job_id,
                stage=t.stage,
                task_type=t.task_type,
                agent_id=t.agent_id,
                state=t.state,
                engine=t.inputs.get("engine"),
                depends_on=list(t.depends_on.get("tasks", [])),
                priority=t.priority,
                attempt_count=t.attempt_count,
                last_error_code=t.last_error_code,
                last_error_class=t.last_error_class,
                lease_owner=t.lease_owner,
                available_at=t.available_at,
                state_changed_at=t.state_changed_at,
                created_at=t.created_at,
                attempts=by_task.get(t.id, []),
            )
        )
    return out


def _check_out(c: CheckRun) -> CheckRunOut:
    return CheckRunOut(
        id=c.id,
        job_id=c.job_id,
        task_id=c.task_id,
        attempt_no=c.attempt_no,
        worker_run_id=c.worker_run_id,
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
        evidence_ids=list(c.evidence.get("items", [])),
    )


def list_checks(session: Session, principal: Principal, job_id: str) -> list[CheckRunOut]:
    job = get_job_row(session, principal, job_id)
    rows = session.execute(
        select(CheckRun).where(CheckRun.job_id == job.id).order_by(CheckRun.started_at, CheckRun.id)
    ).scalars()
    return [_check_out(c) for c in rows]


def list_tests(
    session: Session, principal: Principal, job_id: str, *, status: list[str] | None, limit: int
) -> tuple[list[TestExecutionOut], dict[str, int]]:
    job = get_job_row(session, principal, job_id)
    stmt = select(TestExecution).where(TestExecution.job_id == job.id)
    if status:
        valid = {s.value for s in TestExecutionStatus}
        bad = [s for s in status if s not in valid]
        if bad:
            raise Problem(400, "unsupported_filter", f"Unknown test status(es): {', '.join(bad)}.")
        stmt = stmt.where(TestExecution.status.in_(status))
    rows = list(
        session.execute(
            stmt.order_by(TestExecution.status, TestExecution.node_id).limit(limit)
        ).scalars()
    )
    counts = Counter(
        session.execute(
            select(TestExecution.status).where(TestExecution.job_id == job.id)
        ).scalars()
    )
    return [TestExecutionOut.model_validate(r) for r in rows], dict(counts)


def list_evidence(session: Session, principal: Principal, job_id: str) -> list[EvidenceItemOut]:
    job = get_job_row(session, principal, job_id)
    rows = session.execute(
        select(EvidenceItem).where(EvidenceItem.job_id == job.id).order_by(EvidenceItem.created_at)
    ).scalars()
    return [EvidenceItemOut.model_validate(r) for r in rows]


def list_worker_runs(session: Session, principal: Principal, job_id: str) -> list[WorkerRunOut]:
    job = get_job_row(session, principal, job_id)
    rows = session.execute(
        select(WorkerRun).where(WorkerRun.job_id == job.id).order_by(WorkerRun.started_at)
    ).scalars()
    return [WorkerRunOut.model_validate(r) for r in rows]


def get_evidence(session: Session, principal: Principal, evidence_id: str) -> EvidenceItem:
    item = session.execute(
        select(EvidenceItem).where(
            EvidenceItem.id == evidence_id, EvidenceItem.org_id == principal.org_id
        )
    ).scalar_one_or_none()
    if item is None:
        raise Problem(404, "not_found", "Evidence item not found.")
    return item


def evidence_content(
    session: Session, store: EvidenceStore, principal: Principal, evidence_id: str, inline_max: int
) -> tuple[EvidenceItem, bytes, EvidenceContentOut]:
    item = get_evidence(session, principal, evidence_id)
    try:
        data = store.get(item.org_id, item.sha256)
    except FileNotFoundError as exc:
        raise Problem(404, "not_found", "Evidence object is missing from the store.") from exc
    except EvidenceIntegrityError as exc:
        raise Problem(
            503, "dependency_unavailable", "Evidence object failed its integrity check."
        ) from exc
    text: str | None = None
    truncated_inline = False
    if item.media_type.startswith(TEXT_MEDIA_PREFIXES):
        chunk = data[:inline_max]
        truncated_inline = len(data) > inline_max
        text = chunk.decode("utf-8", errors="replace")
    out = EvidenceContentOut(
        id=item.id,
        media_type=item.media_type,
        sha256=item.sha256,
        size_bytes=item.size_bytes,
        text=text,
        truncated_inline=truncated_inline,
    )
    return item, data, out


def get_report(session: Session, principal: Principal, job_id: str) -> ReportOut:
    job = get_job_row(session, principal, job_id)
    report = session.execute(
        select(Report).where(Report.job_id == job.id, Report.kind == "main")
    ).scalar_one_or_none()
    if report is None:
        # Jobs still running have no stored report yet; compose a partial view on demand without
        # persisting it (the scheduler stores the final one).
        content, digest = compose_report(session, job, partial=True)
        return ReportOut(
            id="",
            job_id=job.id,
            kind="main",
            verdict=None,
            digest=digest,
            partial=True,
            created_at=job.created_at,
            updated_at=job.updated_at,
            content=content,
        )
    return ReportOut.model_validate(report)


def _ref(job: Job) -> CompareJobRef:
    return CompareJobRef(
        id=job.id,
        display_id=job.display_id,
        state=JobState(job.state),
        ref=job.ref,
        commit_sha=job.commit_sha,
        created_at=job.created_at,
    )


def _delta(base: str | None, other: str | None, rank: dict[str, int]) -> str:
    if base is None and other is not None:
        return "added"
    if other is None and base is not None:
        return "removed"
    if base == other:
        return "unchanged"
    return "improved" if rank.get(other or "", -1) > rank.get(base or "", -1) else "regressed"


def compare_jobs(session: Session, principal: Principal, job_id: str, other_id: str) -> CompareOut:
    base = get_job_row(session, principal, job_id)
    other = get_job_row(session, principal, other_id)
    if base.id == other.id:
        raise Problem(400, "bad_request", "Choose a different job to compare with.")

    def checks_of(job: Job) -> dict[tuple[str, str], str]:
        rows = session.execute(
            select(CheckRun).where(CheckRun.job_id == job.id).order_by(CheckRun.started_at)
        ).scalars()
        return {(c.engine_id, c.name): c.outcome for c in rows}

    def tests_of(job: Job) -> dict[str, str]:
        rows = session.execute(
            select(TestExecution).where(TestExecution.job_id == job.id)
        ).scalars()
        return {t.node_id: t.status for t in rows}

    bc, oc = checks_of(base), checks_of(other)
    checks = [
        CompareCheck(
            engine=k[0],
            name=k[1],
            base=bc.get(k),
            other=oc.get(k),
            delta=_delta(bc.get(k), oc.get(k), _CHECK_RANK),
        )
        for k in sorted(set(bc) | set(oc))
    ]
    bt, ot = tests_of(base), tests_of(other)
    tests = [
        CompareTest(
            node_id=n,
            base=bt.get(n),
            other=ot.get(n),
            delta=_delta(bt.get(n), ot.get(n), _TEST_RANK),
        )
        for n in sorted(set(bt) | set(ot))
    ]
    changed = [t for t in tests if t.delta != "unchanged"][:500]
    return CompareOut(
        base=_ref(base),
        other=_ref(other),
        same_repository=base.repository_id == other.repository_id,
        same_commit=bool(base.commit_sha) and base.commit_sha == other.commit_sha,
        checks=checks,
        tests=changed,
        check_deltas=dict(Counter(c.delta for c in checks)),
        test_deltas=dict(Counter(t.delta for t in tests)),
        test_counts={"base": dict(Counter(bt.values())), "other": dict(Counter(ot.values()))},
    )


def list_audit_events(
    session: Session,
    principal: Principal,
    *,
    job_id: str | None,
    actor_id: str | None,
    action: str | None,
    limit: int,
    after: int | None,
) -> tuple[list[AuditEventOut], int | None]:
    stmt = (
        select(AuditEvent)
        .where(AuditEvent.org_id == principal.org_id)
        .order_by(AuditEvent.seq.desc())
    )
    if job_id:
        stmt = stmt.where(AuditEvent.job_id == job_id)
    if actor_id:
        stmt = stmt.where(AuditEvent.actor_id == actor_id)
    if action:
        stmt = stmt.where(AuditEvent.action == action)
    if after is not None:
        stmt = stmt.where(AuditEvent.seq < after)
    rows = list(session.execute(stmt.limit(limit + 1)).scalars())
    next_seq = rows[limit - 1].seq if len(rows) > limit else None
    return [AuditEventOut.model_validate(r) for r in rows[:limit]], next_seq
