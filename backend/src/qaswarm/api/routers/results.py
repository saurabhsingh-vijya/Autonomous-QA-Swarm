"""Plan, tasks, executions, findings, evidence, quality gates and report for a job.

All responses are read from persisted records. Nothing here computes a result on the fly.
"""

from __future__ import annotations

import html
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, Query, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from qaswarm.agents.registry import AGENT_CATALOGUE
from qaswarm.api.auth import Principal, get_principal, require_role
from qaswarm.api.deps import get_db
from qaswarm.api.errors import Problem
from qaswarm.api.etag import etag_for, parse_if_match
from qaswarm.api.schemas import PlanApprovalRequest, ResponseModel
from qaswarm.api.services.jobs import get_job_row
from qaswarm.audit.chain import append_event
from qaswarm.config import Settings, get_settings
from qaswarm.db.models import (
    AgentOutput,
    Approval,
    EvidenceItem,
    Finding,
    Job,
    JobPlan,
    Report,
    Task,
    TaskAttempt,
    TestExecution,
)
from qaswarm.defects.triage import Actor, TriageError, apply_triage
from qaswarm.domain.enums import JobState, Role, TestExecutionStatus
from qaswarm.domain.ids import new_id
from qaswarm.reporting.basic import render_html as render_basic_html
from qaswarm.telemetry.logging import correlation_id_var
from qaswarm.workflow.orchestrator import Orchestrator

router = APIRouter(tags=["results"])


class PlanOut(BaseModel):
    id: str
    job_id: str
    revision: int
    plan_hash: str
    planner: str
    approval_required: bool
    approved_at: datetime | None
    nodes: list[dict[str, Any]]


class AttemptOut(ResponseModel):
    id: str
    attempt_no: int
    lease_owner: str
    outcome: str
    error_code: str | None
    error_class: str | None
    started_at: datetime | None
    ended_at: datetime | None


class AgentOutputOut(ResponseModel):
    id: str
    attempt_no: int
    agent_id: str
    agent_kind: str
    adapter: str
    model_ref: str | None
    schema_name: str
    schema_version: str
    validation_status: str
    input_sha256: str
    output_sha256: str
    tokens_in: int
    tokens_out: int
    duration_ms: int
    payload: dict[str, Any]
    created_at: datetime


class TaskOut(ResponseModel):
    id: str
    job_id: str
    stage: str
    task_type: str
    agent_id: str | None
    state: str
    engine: str | None = None
    priority: int = 0
    attempt_count: int
    depends_on: dict[str, Any]
    inputs: dict[str, Any]
    last_error_code: str | None
    last_error_class: str | None
    lease_owner: str | None = None
    available_at: datetime
    state_changed_at: datetime
    created_at: datetime
    attempts: list[AttemptOut] = []
    outputs: list[AgentOutputOut] = []


class TestExecutionOut(ResponseModel):
    id: str
    job_id: str
    task_id: str
    check_run_id: str | None = None
    node_id: str = ""
    file: str | None = None
    commit_sha: str | None = None
    scenario_id: str | None
    test_type: str
    name: str
    provenance: str
    purpose: str
    status: str
    duration_ms: int
    message: str | None
    meta: dict[str, Any]
    tool: str
    tool_version: str
    evidence_id: str | None
    created_at: datetime


class FindingOut(ResponseModel):
    id: str
    display_id: str
    job_id: str
    category: str
    title: str
    severity: str
    status: str
    confidence: str
    dcs: int
    dcs_breakdown: dict[str, Any]
    fingerprint: str
    location: dict[str, Any]
    occurrences: int
    facts: dict[str, Any]
    inferred: dict[str, Any]
    evidence_ids: dict[str, Any]
    test_execution_ids: dict[str, Any]
    description: str
    affected_tests: dict[str, Any]
    reproducibility: dict[str, Any]
    root_causes: dict[str, Any]
    risk_priority: float
    priority_breakdown: dict[str, Any]
    history: dict[str, Any]
    status_history: dict[str, Any]
    triage: dict[str, Any]
    duplicate_of: str | None
    disputed: bool
    created_at: datetime
    version: int


class TriageRequest(BaseModel):
    action: Literal[
        "mark_false_positive", "accept_risk", "mark_duplicate", "reopen", "request_reproduction"
    ]
    reason: str | None = None
    duplicate_of: str | None = None
    expires_at: datetime | None = None


class EvidenceOut(ResponseModel):
    id: str
    job_id: str
    task_id: str | None
    worker_run_id: str | None = None
    kind: str
    label: str = ""
    media_type: str
    sha256: str
    size_bytes: int
    producer: str
    deterministic: bool
    redactions: int = 0
    truncated: bool = False
    original_bytes: int | None = None
    redaction_status: str
    content: dict[str, Any] | None = None
    created_at: datetime


class ListOut(BaseModel):
    items: list[Any]
    next_cursor: None = None
    limit: int


def _plan(session: Session, job_id: str) -> JobPlan:
    plan = (
        session.execute(
            select(JobPlan).where(JobPlan.job_id == job_id).order_by(JobPlan.revision.desc())
        )
        .scalars()
        .first()
    )
    if plan is None:
        raise Problem(404, "not_found", "This job has no plan yet.")
    return plan


@router.get("/jobs/{job_id}/plan", response_model=PlanOut)
def get_plan(
    job_id: str,
    session: Session = Depends(get_db, scope="function"),
    principal: Principal = Depends(get_principal),
) -> PlanOut:
    job = get_job_row(session, principal, job_id)
    plan = _plan(session, job.id)
    return PlanOut(
        id=plan.id,
        job_id=plan.job_id,
        revision=plan.revision,
        plan_hash=plan.plan_hash,
        planner=plan.planner,
        approval_required=plan.approval_required,
        approved_at=plan.approved_at,
        nodes=plan.dag["nodes"],
    )


@router.post("/jobs/{job_id}/plan/approval", status_code=202)
def approve_plan(
    job_id: str,
    body: PlanApprovalRequest,
    session: Session = Depends(get_db, scope="function"),
    principal: Principal = require_role(Role.QA_LEAD),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    job = get_job_row(session, principal, job_id)
    if job.state != JobState.AWAITING_APPROVAL.value:
        raise Problem(
            409,
            "invalid_state_transition",
            f"Job {job.display_id} is {job.state}, not awaiting approval.",
        )
    plan = _plan(session, job.id)
    approved = body.decision == "approve"
    if not approved and not body.reason:
        raise Problem(422, "validation_failed", "A reason is required to reject a plan.")
    approval = Approval(
        id=new_id("approval"),
        org_id=job.org_id,
        ha_id="HA-05",
        subject_type="job_plan",
        subject_id=plan.id,
        decision="approved" if approved else "rejected",
        approver_id=principal.user_id,
        role_at_decision=principal.role.value,
        reason=body.reason,
        subject_hash=plan.plan_hash,
    )
    session.add(approval)
    append_event(
        session,
        org_id=job.org_id,
        actor_type="user",
        actor_id=principal.user_id,
        actor_role=principal.role.value,
        action="plan.approval_recorded",
        subject_type="job_plan",
        subject_id=plan.id,
        job_id=job.id,
        correlation_id=correlation_id_var.get(),
        details={
            "ha_id": "HA-05",
            "decision": approval.decision,
            "plan_hash": plan.plan_hash,
            "reason": body.reason,
        },
    )
    Orchestrator.from_settings(settings).approve_plan(
        session, job, approved=approved, correlation_id=correlation_id_var.get()
    )
    return {
        "job_id": job.id,
        "state": job.state,
        "approval_id": approval.id,
        "decision": approval.decision,
    }


@router.get("/jobs/{job_id}/tasks", response_model=ListOut)
def list_tasks(
    job_id: str,
    session: Session = Depends(get_db, scope="function"),
    principal: Principal = Depends(get_principal),
) -> ListOut:
    job = get_job_row(session, principal, job_id)
    tasks = (
        session.execute(select(Task).where(Task.job_id == job.id).order_by(Task.created_at))
        .scalars()
        .all()
    )
    attempts = (
        session.execute(
            select(TaskAttempt)
            .where(TaskAttempt.task_id.in_([t.id for t in tasks]))
            .order_by(TaskAttempt.attempt_no)
        )
        .scalars()
        .all()
        if tasks
        else []
    )
    outputs = (
        session.execute(
            select(AgentOutput).where(AgentOutput.job_id == job.id).order_by(AgentOutput.created_at)
        )
        .scalars()
        .all()
    )
    items = []
    for t in tasks:
        out = TaskOut.model_validate(t)
        out.engine = t.inputs.get("engine")
        out.attempts = [AttemptOut.model_validate(a) for a in attempts if a.task_id == t.id]
        out.outputs = [AgentOutputOut.model_validate(o) for o in outputs if o.task_id == t.id]
        items.append(out)
    return ListOut(items=items, limit=len(items))


@router.get("/jobs/{job_id}/test-executions", response_model=ListOut)
def list_executions(
    job_id: str,
    response: Response,
    status: str | None = Query(default=None, description="Comma-separated test statuses"),
    limit: int = Query(default=200, ge=1, le=1000),
    session: Session = Depends(get_db, scope="function"),
    principal: Principal = Depends(get_principal),
) -> ListOut:
    job = get_job_row(session, principal, job_id)
    stmt = (
        select(TestExecution)
        .where(TestExecution.job_id == job.id)
        .order_by(TestExecution.created_at, TestExecution.node_id)
    )
    if status:
        wanted = [s.strip() for s in status.split(",") if s.strip()]
        valid = {s.value for s in TestExecutionStatus}
        bad = [s for s in wanted if s not in valid]
        if bad:
            raise Problem(400, "unsupported_filter", f"Unknown test status(es): {', '.join(bad)}.")
        stmt = stmt.where(TestExecution.status.in_(wanted))
    rows = session.execute(stmt.limit(limit)).scalars().all()
    counts: dict[str, int] = {}
    for st in session.execute(
        select(TestExecution.status).where(TestExecution.job_id == job.id)
    ).scalars():
        counts[st] = counts.get(st, 0) + 1
    response.headers["X-Test-Counts"] = ",".join(f"{k}={v}" for k, v in sorted(counts.items()))
    return ListOut(items=[TestExecutionOut.model_validate(r) for r in rows], limit=len(rows))


def _csv(value: str | None) -> list[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


@router.get("/jobs/{job_id}/findings", response_model=ListOut)
def list_findings(
    job_id: str,
    severity: str | None = Query(default=None),
    confidence: str | None = Query(default=None),
    status: str | None = Query(default=None),
    session: Session = Depends(get_db, scope="function"),
    principal: Principal = Depends(get_principal),
) -> ListOut:
    """Findings sorted by risk priority (design 11/02), then DCS. Filters are comma-separated."""
    job = get_job_row(session, principal, job_id)
    stmt = select(Finding).where(Finding.job_id == job.id)
    if severity:
        stmt = stmt.where(Finding.severity.in_(_csv(severity)))
    if confidence:
        stmt = stmt.where(Finding.confidence.in_(_csv(confidence)))
    if status:
        stmt = stmt.where(Finding.status.in_(_csv(status)))
    rows = (
        session.execute(stmt.order_by(Finding.risk_priority.desc(), Finding.dcs.desc()))
        .scalars()
        .all()
    )
    return ListOut(items=[FindingOut.model_validate(r) for r in rows], limit=len(rows))


def _finding(session: Session, principal: Principal, finding_id: str) -> Finding:
    f = session.execute(
        select(Finding).where(Finding.id == finding_id, Finding.org_id == principal.org_id)
    ).scalar_one_or_none()
    if f is None:
        raise Problem(404, "not_found", "Finding not found.")
    return f


@router.get("/findings/{finding_id}", response_model=FindingOut)
def get_finding(
    finding_id: str,
    response: Response,
    session: Session = Depends(get_db, scope="function"),
    principal: Principal = Depends(get_principal),
) -> FindingOut:
    f = _finding(session, principal, finding_id)
    response.headers["ETag"] = etag_for(f.id, f.version)
    return FindingOut.model_validate(f)


@router.post("/findings/{finding_id}/triage", response_model=FindingOut)
def triage_finding(
    finding_id: str,
    body: TriageRequest,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    session: Session = Depends(get_db, scope="function"),
    principal: Principal = Depends(get_principal),
) -> FindingOut:
    """Change a finding's status (FR-037). Roles and reasons are enforced in
    ``qaswarm.defects.triage``; every change is audited and bumps the version/ETag."""
    f = _finding(session, principal, finding_id)
    expected = parse_if_match(if_match, f.id)
    if expected is not None and expected != f.version:
        raise Problem(412, "etag_mismatch", "The finding changed since you read it; re-read it.")
    try:
        apply_triage(
            session,
            f,
            action=body.action,
            actor=Actor(user_id=principal.user_id, role=principal.role),
            reason=body.reason,
            duplicate_of=body.duplicate_of,
            expires_at=body.expires_at,
            correlation_id=correlation_id_var.get(),
        )
    except TriageError as exc:
        raise Problem(exc.status, exc.code, exc.detail, **exc.extra) from exc
    response.headers["ETag"] = etag_for(f.id, f.version)
    return FindingOut.model_validate(f)


@router.get("/findings/{finding_id}/history", response_model=ListOut)
def get_finding_history(
    finding_id: str,
    session: Session = Depends(get_db, scope="function"),
    principal: Principal = Depends(get_principal),
) -> ListOut:
    """Every finding with the same fingerprint on the same repository, newest first."""
    f = _finding(session, principal, finding_id)
    job = session.get(Job, f.job_id)
    rows = (
        session.execute(
            select(Finding)
            .join(Job, Job.id == Finding.job_id)
            .where(
                Finding.org_id == f.org_id,
                Finding.fingerprint == f.fingerprint,
                Job.repository_id == (job.repository_id if job else None),
            )
            .order_by(Finding.created_at.desc())
        )
        .scalars()
        .all()
    )
    return ListOut(items=[FindingOut.model_validate(r) for r in rows], limit=len(rows))


@router.get("/findings/{finding_id}/evidence", response_model=ListOut)
def get_finding_evidence(
    finding_id: str,
    session: Session = Depends(get_db, scope="function"),
    principal: Principal = Depends(get_principal),
) -> ListOut:
    f = _finding(session, principal, finding_id)
    ids = list(f.evidence_ids.get("items", []))
    rows = (
        session.execute(select(EvidenceItem).where(EvidenceItem.id.in_(ids))).scalars().all()
        if ids
        else []
    )
    return ListOut(items=[EvidenceOut.model_validate(r) for r in rows], limit=len(rows))


@router.get("/jobs/{job_id}/evidence", response_model=ListOut)
def list_job_evidence(
    job_id: str,
    session: Session = Depends(get_db, scope="function"),
    principal: Principal = Depends(get_principal),
) -> ListOut:
    job = get_job_row(session, principal, job_id)
    rows = (
        session.execute(
            select(EvidenceItem)
            .where(EvidenceItem.job_id == job.id)
            .order_by(EvidenceItem.created_at)
        )
        .scalars()
        .all()
    )
    return ListOut(items=[EvidenceOut.model_validate(r) for r in rows], limit=len(rows))


def _report(session: Session, job_id: str) -> Report:
    report = session.execute(
        select(Report).where(Report.job_id == job_id, Report.kind == "main")
    ).scalar_one_or_none()
    if report is None:
        raise Problem(404, "not_found", "No report has been generated for this job yet.")
    return report


@router.get("/jobs/{job_id}/quality-gates")
def quality_gates(
    job_id: str,
    session: Session = Depends(get_db, scope="function"),
    principal: Principal = Depends(get_principal),
) -> dict[str, Any]:
    job = get_job_row(session, principal, job_id)
    report = session.execute(
        select(Report).where(Report.job_id == job.id, Report.kind == "main")
    ).scalar_one_or_none()
    if report is None:
        gates = [
            {"gate_id": f"QG-0{i}", "result": "pending", "blocking": i != 6} for i in range(1, 9)
        ]
        return {
            "job_id": job.id,
            "display_id": job.display_id,
            "evaluated_at": None,
            "verdict": None,
            "verdict_reason": "Gates are evaluated when the report is produced.",
            "gates": gates,
            "accepted_risks": [],
            "release_decision": None,
        }
    c = report.content
    return {
        "job_id": job.id,
        "display_id": job.display_id,
        "evaluated_at": c.get("generated_at"),
        "verdict": c["verdict"],
        "verdict_reason": c["verdict_reason"],
        "gates": c["gates"],
        "accepted_risks": [],
        "release_decision": None,
        "report_digest": report.digest,
    }


def _render_html(job_display: str, content: dict[str, Any], digest: str) -> str:
    e = html.escape
    gates = "".join(
        f"<tr><td>{e(g['gate_id'])}</td><td>{e(g['result'])}</td><td>{'yes' if g['blocking'] else 'advisory'}</td>"
        f"<td>{e(str(g.get('measured', '')))}</td><td>{e(g.get('note') or '')}</td></tr>"
        for g in content["gates"]
    )
    ts = content["test_summary"]
    residual = "".join(f"<li>{e(r)}</li>" for r in content["residual_risk"])
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>RaOne report {e(job_display)}</title>
<style>body{{font:14px/1.5 system-ui;margin:2rem;color:#141a22}}
table{{border-collapse:collapse}}td,th{{border:1px solid #dee3ea;padding:4px 8px;text-align:left}}
</style></head>
<body><h1>RaOne QA report {e(job_display)}</h1>
<p><strong>Verdict: {e(content['verdict'])}</strong> — {e(content['verdict_reason'])}</p>
<h2>Quality gates</h2><table>
<tr><th>Gate</th><th>Result</th><th>Blocking</th><th>Measured</th><th>Note</th></tr>{gates}</table>
<h2>Test summary</h2><p>executed {ts.get('executed', 0)}, passed {ts.get('passed', 0)},
failed {ts.get('failed', 0)}, skipped {ts.get('skipped', 0)}, blocked {ts.get('blocked', 0)}</p>
<h2>Residual risk</h2><ul>{residual}</ul>
<h2>Narrative</h2><p>{e(content['narrative'])}</p><p><em>Source: {e(content['narrative_source'])}</em></p>
<p>Report digest {e(digest)} · generated {e(str(content.get('generated_at')))}</p></body></html>"""


@router.get(
    "/jobs/{job_id}/report",
    responses={200: {"content": {"text/html": {}}}, 501: {"description": "format not built yet"}},
)
def get_report(
    job_id: str,
    format: str = Query(default="json", pattern="^(json|html|pdf|sarif|junit)$"),
    session: Session = Depends(get_db, scope="function"),
    principal: Principal = Depends(get_principal),
) -> Response:
    """The stored report: AG-11's full report, or the deterministic partial report written when a
    job fails or is cancelled before the report agent ran."""
    job = get_job_row(session, principal, job_id)
    if format not in ("json", "html"):
        raise Problem(
            501,
            "not_implemented",
            f"Report format '{format}' is planned for slice 2d and is not implemented in this build.",
            planned_slice="2d",
        )
    report = _report(session, job.id)
    if format == "html":
        if report.partial or "gates" not in report.content:
            return HTMLResponse(render_basic_html(report.content))
        return HTMLResponse(_render_html(job.display_id, report.content, report.digest))
    from fastapi.responses import JSONResponse

    return JSONResponse(
        {
            "id": report.id,
            "job_id": job.id,
            "kind": report.kind,
            "verdict": report.verdict,
            "generator": report.generator,
            "partial": report.partial,
            "digest": report.digest,
            "created_at": report.created_at.isoformat().replace("+00:00", "Z"),
            "updated_at": report.updated_at.isoformat().replace("+00:00", "Z"),
            "content": report.content,
        }
    )


@router.get("/system/agents")
def agent_registry(
    principal: Principal = Depends(get_principal), settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    return {
        "llm_provider": settings.llm_provider,
        "note": (
            "Agents labelled deterministic never call a model. LLM-assisted agents use a local "
            "provider only when AQS_LLM_PROVIDER is set."
        ),
        "items": [
            {
                "agent_id": a.agent_id,
                "name": a.name,
                "kind": a.kind.value,
                "stage": a.stage,
                "implemented": a.implemented,
                "adapter": a.adapter,
                "planned_slice": a.planned_slice,
                "task_types": list(a.task_types),
            }
            for a in AGENT_CATALOGUE
        ],
    }
