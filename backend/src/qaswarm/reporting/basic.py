from __future__ import annotations

import hashlib
import html
import json
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from qaswarm.db.models import CheckRun, EvidenceItem, Job, Report, Repository, Task, TestExecution
from qaswarm.domain.enums import TaskState
from qaswarm.domain.ids import new_id

WARNING_TASK_STATES = {
    TaskState.SKIPPED.value,
    TaskState.TIMED_OUT.value,
    TaskState.FAILED.value,
    TaskState.INVALID_OUTPUT.value,
    TaskState.CANCELLED.value,
}


def _iso(dt: datetime | None) -> str | None:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z") if dt else None


def build_report(session: Session, job: Job, *, partial: bool = False) -> Report:
    """Compose and persist the ``main`` report row for a job (upsert)."""
    content, digest = compose_report(session, job, partial=partial)
    report = session.execute(
        select(Report).where(Report.job_id == job.id, Report.kind == "main")
    ).scalar_one_or_none()
    if report is None:
        report = Report(id=new_id("report"), org_id=job.org_id, job_id=job.id, kind="main")
        session.add(report)
    report.content = content
    report.digest = digest
    report.partial = partial
    report.verdict = None
    report.generator = "basic-partial" if partial else "basic"
    session.flush()
    return report


def compose_report(
    session: Session, job: Job, *, partial: bool = False
) -> tuple[dict[str, Any], str]:
    """Assemble the JSON report from stored rows (deterministic; no narrative in this phase)."""
    repo = session.execute(
        select(Repository).where(Repository.id == job.repository_id)
    ).scalar_one()
    tasks = list(
        session.execute(
            select(Task).where(Task.job_id == job.id).order_by(Task.created_at)
        ).scalars()
    )
    checks = list(
        session.execute(
            select(CheckRun).where(CheckRun.job_id == job.id).order_by(CheckRun.started_at)
        ).scalars()
    )
    tests = list(
        session.execute(select(TestExecution).where(TestExecution.job_id == job.id)).scalars()
    )
    evidence = list(
        session.execute(select(EvidenceItem).where(EvidenceItem.job_id == job.id)).scalars()
    )
    task_counts = Counter(t.state for t in tasks)
    check_counts = Counter(c.outcome for c in checks)
    test_counts = Counter(t.status for t in tests)
    warnings: list[str] = list(job.warnings.get("items", []))
    for t in tasks:
        if t.state in WARNING_TASK_STATES:
            warnings.append(f"task {t.task_type}:{t.inputs.get('engine', '')} ended {t.state}")
    content: dict[str, Any] = {
        "schema_version": "1.0",
        "generated_at": _iso(datetime.now(UTC)),
        "partial": partial,
        "job": {
            "id": job.id,
            "display_id": job.display_id,
            "state": job.state,
            "repository": repo.url,
            "ref": job.ref,
            "commit_sha": job.commit_sha,
            "snapshot_sha256": job.snapshot_sha256,
            "profiles": job.profiles,
            "started_at": _iso(job.started_at),
            "ended_at": _iso(job.ended_at),
        },
        "summary": {
            "tasks": dict(task_counts),
            "checks": dict(check_counts),
            "tests": dict(test_counts),
        },
        "checks": [
            {
                "id": c.id,
                "engine": c.engine_id,
                "name": c.name,
                "outcome": c.outcome,
                "duration_ms": c.duration_ms,
                "failure_message": c.failure_message,
                "summary": c.summary,
                "tool": {"name": c.tool_name, "version": c.tool_version},
                "executes_repository_code": c.executes_repository_code,
                "evidence_ids": list(c.evidence.get("items", [])),
            }
            for c in checks
        ],
        "tests": [
            {
                "node_id": t.node_id,
                "status": t.status,
                "duration_ms": t.duration_ms,
                "message": t.message,
                "file": t.file,
            }
            for t in tests
        ],
        "evidence": [
            {
                "id": e.id,
                "kind": e.kind,
                "label": e.label,
                "sha256": e.sha256,
                "size_bytes": e.size_bytes,
                "media_type": e.media_type,
                "redactions": e.redactions,
                "truncated": e.truncated,
            }
            for e in evidence
        ],
        "warnings": warnings,
        "limitations": [
            "Checks ran in a subprocess runtime, not a sandbox (no gVisor/Docker on this build).",
            "Quality gates, findings and the Defect Confidence Score are not evaluated yet "
            "(slices 2b/2d).",
        ],
        "verdict": None,
    }
    digest = hashlib.sha256(
        json.dumps(content, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
    return content, digest


def render_html(content: dict[str, Any]) -> str:
    """Self-contained HTML rendered from the JSON report (no external assets)."""
    e = html.escape
    job = content["job"]
    rows = "".join(
        f"<tr><td>{e(str(c['engine']))}</td><td>{e(str(c['name']))}</td>"
        f"<td class='o-{e(str(c['outcome']))}'>{e(str(c['outcome']))}</td>"
        f"<td>{c['duration_ms']} ms</td><td>{e(str(c['failure_message'] or ''))}</td></tr>"
        for c in content["checks"]
    )
    tests = "".join(
        f"<tr><td>{e(str(t['node_id']))}</td><td>{e(str(t['status']))}</td>"
        f"<td>{t['duration_ms']} ms</td><td>{e(str(t['message'] or ''))}</td></tr>"
        for t in content["tests"]
    )
    warn = "".join(f"<li>{e(str(w))}</li>" for w in content["warnings"]) or "<li>none</li>"
    lim = "".join(f"<li>{e(str(w))}</li>" for w in content["limitations"])
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>QA report {e(str(job["display_id"]))}</title>
<style>body{{font:14px system-ui,sans-serif;margin:2rem;color:#0f172a}}
table{{border-collapse:collapse;width:100%;margin:1rem 0}}
td,th{{border:1px solid #e2e8f0;padding:.4rem;text-align:left;font-size:13px}}th{{background:#f8fafc}}
.o-passed{{color:#047857}}.o-failed{{color:#b91c1c}}.o-error{{color:#c2410c}}.o-skipped{{color:#475569}}
code{{font-family:ui-monospace,monospace}}</style></head><body>
<h1>QA report · {e(str(job["display_id"]))}{" (partial)" if content["partial"] else ""}</h1>
<p><code>{e(str(job["repository"]))}</code> · {e(str(job["ref"]))} → <code>{e(str(job["commit_sha"]))}</code>
· snapshot <code>{e(str(job["snapshot_sha256"]))}</code> · state {e(str(job["state"]))}</p>
<p>Verdict: <strong>not evaluated</strong> (quality gates arrive in slice 2d).
Generated {e(str(content["generated_at"]))}.</p>
<h2>Checks</h2><table><tr><th>Engine</th><th>Check</th><th>Outcome</th><th>Duration</th>
<th>Message</th></tr>{rows}</table>
<h2>Tests ({len(content["tests"])})</h2><table><tr><th>Test</th><th>Status</th><th>Duration</th>
<th>Message</th></tr>{tests}</table>
<h2>Warnings</h2><ul>{warn}</ul><h2>Limitations</h2><ul>{lim}</ul>
<p>Evidence objects: {len(content["evidence"])} (content-addressed, redacted before storage).</p>
</body></html>"""
