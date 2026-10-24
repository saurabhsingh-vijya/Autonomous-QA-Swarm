"""End-to-end orchestration against PostgreSQL: real flow, persistence, aggregation, failures,
approval and cancellation."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from qaswarm.agents import registry as agent_registry
from qaswarm.agents.api_testing import HttpChecker
from qaswarm.agents.base import AgentFailure
from qaswarm.config import Settings
from qaswarm.db.models import AgentOutput, EvidenceItem, Finding, Job, Report, Task, TestExecution
from qaswarm.db.session import session_factory
from qaswarm.domain.enums import ErrorClass
from qaswarm.intake.resolvers import IntakeError
from qaswarm.workflow.orchestrator import Orchestrator
from qaswarm.workflow.scheduler import Scheduler

pytestmark = pytest.mark.integration


def _transport(method: str, url: str) -> tuple[int, dict[str, str], str]:
    if url.endswith("/ok"):
        return 200, {"content-type": "application/json", "authorization": "Bearer x"}, '{"ok":true}'
    return 500, {}, "boom"


def _unreachable(url: str) -> object:
    """Resolver factory for repositories that cannot be contacted in tests (no network)."""
    raise IntakeError("E-INTAKE-002", "unreachable", "no network in tests", policy=False)


def _orch(settings: Settings) -> Orchestrator:
    return Orchestrator.from_settings(settings, http=HttpChecker(transport=_transport))


def _sched(settings: Settings) -> Scheduler:
    return Scheduler(settings, resolver_factory=_unreachable)


def _run(settings: Settings, session, job_id: str, **kw):  # type: ignore[no-untyped-def]
    return _orch(settings).run_job_to_completion(session, job_id, scheduler=_sched(settings), **kw)


def _repo(client: TestClient, headers: dict) -> str:
    p = client.post(
        "/api/v1/projects", json={"name": f"P-{uuid.uuid4().hex[:6]}"}, headers=headers
    ).json()
    r = client.post(
        "/api/v1/repositories",
        headers=headers,
        json={
            "project_id": p["id"],
            "provider": "github",
            "url": f"https://github.com/o/{uuid.uuid4().hex[:8]}",
        },
    )
    return r.json()["id"]


def _create(client: TestClient, headers: dict, repo: str, **extra) -> dict:  # type: ignore[no-untyped-def]
    body = {
        "repository_id": repo,
        "ref": "main",
        "profiles": {"functional": "standard", "security": "none", "performance": "none"},
        "inputs": {
            "requirements": ["The service must answer health checks"],
            "api_checks": [
                {
                    "method": "GET",
                    "url": "http://localhost:8000/ok",
                    "expected_status": 200,
                    "priority": "P0",
                },
                {"method": "GET", "url": "http://localhost:8000/broken", "expected_status": 200},
                {"method": "POST", "url": "http://localhost:8000/ok", "expected_status": 200},
            ],
        },
        **extra,
    }
    r = client.post(
        "/api/v1/jobs", json=body, headers={**headers, "Idempotency-Key": uuid.uuid4().hex}
    )
    assert r.status_code == 202, r.text
    return r.json()


def test_single_job_runs_a_real_orchestration_flow_and_persists_everything(
    client: TestClient, auth_headers: dict, test_settings: Settings
) -> None:
    repo = _repo(client, auth_headers)
    job = _create(client, auth_headers, repo)
    assert job["state"] == "validating" and "Intake" in job["held_reason"]

    with session_factory()() as s:
        done = _run(test_settings, s, job["id"])
        assert (
            done.state == "completed_with_warnings"
        )  # functional scenario skipped, one check failed, repository not pinned
        assert done.commit_sha is None and any(
            "could not be pinned" in w for w in done.warnings["items"]
        )
        tasks = s.execute(select(Task).where(Task.job_id == job["id"])).scalars().all()
        assert {t.agent_id: t.state for t in tasks} == {
            "AG-02": "succeeded",
            "AG-03": "succeeded",
            "AG-04": "succeeded",
            "AG-08": "succeeded",
            "AG-11": "succeeded",
        }
        outputs = (
            s.execute(select(AgentOutput).where(AgentOutput.job_id == job["id"])).scalars().all()
        )
        assert len(outputs) == 5 and all(
            o.validation_status == "valid" and o.adapter == "deterministic" for o in outputs
        )
        assert all(o.model_ref is None and o.agent_kind == "deterministic" for o in outputs)
        execs = (
            s.execute(select(TestExecution).where(TestExecution.job_id == job["id"]))
            .scalars()
            .all()
        )
        statuses = sorted(e.status for e in execs)
        assert statuses == ["blocked", "failed", "passed", "skipped"]
        evidence = (
            s.execute(select(EvidenceItem).where(EvidenceItem.job_id == job["id"])).scalars().all()
        )
        assert len(evidence) == 2 and all(len(e.sha256) == 64 for e in evidence)
        assert "Bearer x" not in str([e.content for e in evidence])
        findings = s.execute(select(Finding).where(Finding.job_id == job["id"])).scalars().all()
        assert (
            len(findings) == 1
            and findings[0].confidence == "probable"
            and findings[0].display_id.startswith("FND-")
        )
        report = s.execute(select(Report).where(Report.job_id == job["id"])).scalar_one()
        assert report.verdict in ("NOT_READY", "INCONCLUSIVE")
        assert report.content["test_summary"]["executed"] == 2

    # Everything is visible through the API, read from persisted records.
    detail = client.get(f"/api/v1/jobs/{job['id']}", headers=auth_headers).json()
    assert (
        detail["state"] == "completed_with_warnings"
        and detail["report_available"]
        and detail["plan_available"]
    )
    stage = {s["stage"]: s["status"] for s in detail["stages"]}
    assert stage["planning"] == "succeeded" and stage["functional_and_api_testing"] == "succeeded"
    assert (
        stage["quality_gates_and_reporting"] == "succeeded"
        and stage["security_testing"] == "not_planned"
    )
    tasks_api = client.get(f"/api/v1/jobs/{job['id']}/tasks", headers=auth_headers).json()["items"]
    assert len(tasks_api) == 5 and all(t["attempts"] and t["outputs"] for t in tasks_api)
    assert (
        client.get(
            f"/api/v1/jobs/{job['id']}/test-executions?status=failed", headers=auth_headers
        ).json()["limit"]
        == 1
    )
    f = client.get(f"/api/v1/jobs/{job['id']}/findings", headers=auth_headers).json()["items"][0]
    ev = client.get(f"/api/v1/findings/{f['id']}/evidence", headers=auth_headers).json()["items"]
    assert ev and ev[0]["kind"] == "http_exchange"
    # Agent evidence is also stored as an object, so the generic evidence endpoints work.
    ev_meta = client.get(f"/api/v1/evidence/{ev[0]['id']}/content", headers=auth_headers).json()
    assert ev_meta["sha256"] == ev[0]["sha256"] and "response" in (ev_meta["text"] or "")
    gates = client.get(f"/api/v1/jobs/{job['id']}/quality-gates", headers=auth_headers).json()
    assert gates["verdict"] == report.verdict and len(gates["gates"]) == 8
    rep = client.get(f"/api/v1/jobs/{job['id']}/report", headers=auth_headers).json()
    assert rep["digest"] == report.digest and rep["content"]["narrative_source"].startswith(
        "deterministic"
    )
    html = client.get(f"/api/v1/jobs/{job['id']}/report?format=html", headers=auth_headers)
    assert html.status_code == 200 and "RaOne QA report" in html.text
    plan = client.get(f"/api/v1/jobs/{job['id']}/plan", headers=auth_headers).json()
    assert [n["key"] for n in plan["nodes"]] == [
        "requirements",
        "functional",
        "api",
        "evidence",
        "report",
    ]


def test_job_without_inputs_is_held_honestly(
    client: TestClient, auth_headers: dict, test_settings: Settings
) -> None:
    repo = _repo(client, auth_headers)
    r = client.post(
        "/api/v1/jobs",
        json={"repository_id": repo, "ref": "main"},
        headers={**auth_headers, "Idempotency-Key": uuid.uuid4().hex},
    )
    assert r.status_code == 202 and r.json()["state"] == "validating"
    assert "Intake" in r.json()["held_reason"]
    # Without inputs and without a reachable repository there is nothing to run: the job fails
    # honestly at intake instead of pretending.
    with session_factory()() as s:
        done = _run(test_settings, s, r.json()["id"])
        assert done.state == "failed" and done.commit_sha is None


def test_failed_agent_is_retried_then_job_fails_on_critical_path(
    client: TestClient, auth_headers: dict, test_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Flaky:
        agent_id = "AG-02"
        name = "Requirements Analysis Agent"
        kind = agent_registry.RequirementsAnalysisAgent.kind
        task_types = ("requirements.analyze",)
        output_model = agent_registry.RequirementsAnalysisAgent.output_model

        def run(self, task, ctx):  # type: ignore[no-untyped-def]
            raise AgentFailure(
                "provider down",
                error_code="E-MODEL-001",
                retryable=True,
                error_class=ErrorClass.INFRASTRUCTURE_ERROR,
            )

    monkeypatch.setattr(
        agent_registry,
        "_BY_TASK_TYPE",
        {**agent_registry._BY_TASK_TYPE, "requirements.analyze": Flaky()},
    )
    repo = _repo(client, auth_headers)
    job = _create(client, auth_headers, repo)
    settings = test_settings.model_copy(update={"backoff_seconds": [0, 0]})
    with session_factory()() as s:
        done = _run(settings, s, job["id"], max_steps=30)
        assert done.state == "failed"
        task = s.execute(
            select(Task).where(Task.job_id == job["id"], Task.task_type == "requirements.analyze")
        ).scalar_one()
        assert (
            task.state == "failed"
            and task.attempt_count == 3
            and task.last_error_class == "infrastructure_error"
        )
        outputs = (
            s.execute(select(AgentOutput).where(AgentOutput.task_id == task.id)).scalars().all()
        )
        assert len(outputs) == 3 and all(o.validation_status == "failed" for o in outputs)
        others = (
            s.execute(select(Task).where(Task.job_id == job["id"], Task.id != task.id))
            .scalars()
            .all()
        )
        assert {t.state for t in others} == {"skipped"}
        partial = s.execute(select(Report).where(Report.job_id == job["id"])).scalar_one()
        assert partial.partial is True and partial.generator == "basic-partial"


def test_plan_approval_gate_requires_qa_lead_and_rejection_cancels(
    client: TestClient, auth_headers: dict, engineer_headers: dict, test_settings: Settings
) -> None:
    repo = _repo(client, auth_headers)
    job = _create(client, auth_headers, repo, require_plan_approval=True)
    with session_factory()() as s:
        held = _run(test_settings, s, job["id"])
        assert held.state == "awaiting_approval" and "HA-05" in held.held_reason
        assert s.execute(select(Task).where(Task.job_id == job["id"])).scalars().all() == []
    denied = client.post(
        f"/api/v1/jobs/{job['id']}/plan/approval",
        json={"decision": "approve"},
        headers=engineer_headers,
    )
    assert denied.status_code == 403
    no_reason = client.post(
        f"/api/v1/jobs/{job['id']}/plan/approval", json={"decision": "reject"}, headers=auth_headers
    )
    assert no_reason.status_code == 422
    rejected = client.post(
        f"/api/v1/jobs/{job['id']}/plan/approval",
        json={"decision": "reject", "reason": "scope"},
        headers=auth_headers,
    )
    assert rejected.status_code == 202 and rejected.json()["state"] == "cancelled"

    job2 = _create(client, auth_headers, repo, require_plan_approval=True, ref="v2")
    with session_factory()() as s:
        assert _run(test_settings, s, job2["id"]).state == "awaiting_approval"
    ok = client.post(
        f"/api/v1/jobs/{job2['id']}/plan/approval",
        json={"decision": "approve"},
        headers=auth_headers,
    )
    assert ok.status_code == 202 and ok.json()["state"] == "running"
    with session_factory()() as s:
        done = _run(test_settings, s, job2["id"])
        assert done.state == "completed_with_warnings"


def test_cancel_during_run_marks_remaining_tasks_cancelled(
    client: TestClient, auth_headers: dict, test_settings: Settings
) -> None:
    repo = _repo(client, auth_headers)
    job = _create(client, auth_headers, repo)
    with session_factory()() as s:
        _sched(test_settings).tick()  # intake (unpinned) + plan
        _sched(test_settings).tick()
        orch = _orch(test_settings)
        assert orch.run_once(s) == 1  # requirements task done
    r = client.post(
        f"/api/v1/jobs/{job['id']}/cancel", json={"reason": "stop"}, headers=auth_headers
    )
    assert r.status_code == 202 and r.json()["state"] == "cancelled"
    with session_factory()() as s:
        states = {
            t.task_type: t.state
            for t in s.execute(select(Task).where(Task.job_id == job["id"])).scalars()
        }
        assert states["requirements.analyze"] == "succeeded"
        assert all(v == "cancelled" for k, v in states.items() if k != "requirements.analyze")
        assert orch.run_once(s) == 0  # nothing leasable after cancellation
        assert s.get(Job, job["id"]).state == "cancelled"


def test_agent_registry_endpoint_reports_kinds_and_provider(
    client: TestClient, auth_headers: dict
) -> None:
    body = client.get("/api/v1/system/agents", headers=auth_headers).json()
    assert body["llm_provider"] == "none" and len(body["items"]) == 11
    assert [a["agent_id"] for a in body["items"] if a["implemented"]] == [
        "AG-01",
        "AG-02",
        "AG-03",
        "AG-04",
        "AG-08",
        "AG-11",
    ]
