"""Phase 2 integration tests: the real pipeline against PostgreSQL with an in-process exec worker.

Scheduler ticks are driven explicitly; the Execution Service worker talks to the API through the
FastAPI TestClient exactly as it would over HTTP (lease, heartbeat, evidence, result, destroyed).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from qaswarm_exec.host.client import ControlPlaneClient, LeaseLostError
from qaswarm_exec.host.worker import ExecWorker
from qaswarm_exec.runtime.subprocess_runtime import SubprocessRuntime
from sqlalchemy import Engine, select

from qaswarm.api.app import create_app
from qaswarm.audit.chain import verify_chain
from qaswarm.config import Settings, get_settings
from qaswarm.db.models import Task, WorkerRun
from qaswarm.db.session import session_scope
from qaswarm.workflow.queue import TaskQueue
from qaswarm.workflow.scheduler import Scheduler, run_until_idle

pytestmark = pytest.mark.integration

FIXTURES = str(Path(__file__).resolve().parents[3] / "exec" / "fixtures")
TOKEN = "test-exec-token"
LEAD = {"X-Dev-User": "usr_lead", "X-Dev-Role": "QA Lead"}
VIEWER = {"X-Dev-User": "usr_viewer", "X-Dev-Role": "Viewer"}


@pytest.fixture
def settings(tmp_path: Path, test_settings: Settings) -> Settings:
    return Settings(
        database_url=test_settings.database_url,
        dev_auth=True,
        exec_token=TOKEN,
        evidence_dir=str(tmp_path / "evidence"),
        dev_fixture_repos=True,
        fixtures_dir=FIXTURES,
        intake_dns_check=False,
        backoff_seconds=[0, 0],
        backoff_jitter=0.0,
        lease_ttl_seconds=90,
        task_wall_clock_seconds=120,
        sse_heartbeat_seconds=1,
    )


@pytest.fixture
def client(clean_db: Engine, settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _worker(
    client: TestClient, settings: Settings, tmp_path: Path, *, allow: bool, worker_id: str = "w1"
) -> ExecWorker:
    return ExecWorker(
        ControlPlaneClient(client, TOKEN),
        SubprocessRuntime(),
        worker_id=worker_id,
        workspace_root=tmp_path / "ws",
        allow_code_execution=allow,
        fixtures_dir=settings.fixtures_dir,
        heartbeat_seconds=60,
    )


def _repo(client: TestClient, name: str = "sample-python-app") -> dict[str, Any]:
    project = client.post(
        "/api/v1/projects", json={"name": f"P-{uuid.uuid4().hex[:6]}"}, headers=LEAD
    ).json()
    r = client.post(
        "/api/v1/repositories",
        json={
            "project_id": project["id"],
            "provider": "other",
            "url": f"https://fixtures.local/local/{name}",
        },
        headers=LEAD,
    )
    assert r.status_code == 201, r.text
    return r.json()


def _job(
    client: TestClient, repo_id: str, ref: str = "main", profiles: dict[str, str] | None = None
) -> dict[str, Any]:
    body: dict[str, Any] = {"repository_id": repo_id, "ref": ref}
    if profiles:
        body["profiles"] = profiles
    r = client.post(
        "/api/v1/jobs", json=body, headers={**LEAD, "Idempotency-Key": uuid.uuid4().hex}
    )
    assert r.status_code == 202, r.text
    return r.json()


def _drive(
    client: TestClient, settings: Settings, worker: ExecWorker, job_id: str, *, max_rounds: int = 30
) -> dict[str, Any]:
    """Alternate scheduler ticks and worker leases until the job is terminal."""
    scheduler = Scheduler(settings)
    for _ in range(max_rounds):
        run_until_idle(scheduler, max_ticks=10)
        while worker.run_once():
            pass
        run_until_idle(scheduler, max_ticks=10)
        job = client.get(f"/api/v1/jobs/{job_id}", headers=LEAD).json()
        if job["state"] in {
            "completed",
            "completed_with_warnings",
            "failed",
            "cancelled",
            "timed_out",
            "blocked",
        }:
            return job
    raise AssertionError(f"job did not finish: {job}")


# ------------------------------------------------------------------ happy path
def test_full_pipeline_runs_real_checks_and_persists_everything(
    client: TestClient, settings: Settings, tmp_path: Path
) -> None:
    repo = _repo(client)
    job = _job(
        client,
        repo["id"],
        profiles={"functional": "standard", "security": "none", "performance": "none"},
    )
    assert job["state"] == "validating"

    # Duplicate submission while active → 409; the scheduler has not touched the job yet.
    dup = client.post(
        "/api/v1/jobs",
        json={
            "repository_id": repo["id"],
            "ref": "main",
            "profiles": {"functional": "standard", "security": "none", "performance": "none"},
        },
        headers={**LEAD, "Idempotency-Key": uuid.uuid4().hex},
    )
    assert dup.status_code == 409 and dup.json()["existing_job"]["id"] == job["id"]

    final = _drive(client, settings, _worker(client, settings, tmp_path, allow=True), job["id"])
    assert final["state"] == "completed", final
    assert final["commit_sha"] and len(final["commit_sha"]) == 40 and final["snapshot_sha256"]
    assert final["task_summary"] == {"succeeded": 4}
    assert final["check_summary"] == {
        "passed": 2,
        "failed": 2,
    }  # env fetch + integrity pass; syntax + pytest fail
    assert final["test_summary"] == {"passed": 5, "failed": 2}
    stages = {s["stage"]: s["status"] for s in final["stages"]}
    # Tasks succeeded even though checks failed: test failures are results, not task errors.
    assert stages["intake_and_pinning"] == "succeeded" and stages["baseline_run"] == "succeeded"
    assert (
        stages["security_testing"] == "skipped" and stages["cleanup_and_retention"] == "succeeded"
    )

    checks = client.get(f"/api/v1/jobs/{job['id']}/checks", headers=LEAD).json()
    by_engine = {c["engine_id"]: c for c in checks}
    assert set(by_engine) == {"env_prepare", "snapshot_integrity", "python_syntax", "pytest"}
    assert (
        by_engine["pytest"]["outcome"] == "failed"
        and "test_rounds_half_even" in by_engine["pytest"]["failure_message"]
    )
    assert (
        by_engine["pytest"]["executes_repository_code"] is True
        and by_engine["pytest"]["duration_ms"] >= 0
    )
    assert (
        by_engine["python_syntax"]["outcome"] == "failed"
        and "legacy_report.py" in by_engine["python_syntax"]["failure_message"]
    )
    assert all(c["started_at"] <= c["ended_at"] and c["log_evidence_id"] for c in checks)

    tests = client.get(f"/api/v1/jobs/{job['id']}/test-executions?status=failed", headers=LEAD)
    assert tests.status_code == 200 and {t["name"] for t in tests.json()["items"]} == {
        "test_rounds_half_even",
        "test_rejects_sub_minor_unit_amount",
    }
    assert (
        "failed=2" in tests.headers["X-Test-Counts"]
        and "passed=5" in tests.headers["X-Test-Counts"]
    )
    failed = tests.json()["items"][0]
    assert failed["message"] and failed["commit_sha"] == final["commit_sha"]

    tasks = client.get(f"/api/v1/jobs/{job['id']}/tasks", headers=LEAD).json()
    assert len(tasks) == 4 and all(t["attempts"][0]["outcome"] == "succeeded" for t in tasks)
    env = next(t for t in tasks if t["task_type"] == "env_prepare")
    assert all(env["id"] in t["depends_on"] for t in tasks if t["task_type"] == "check")

    evidence = client.get(f"/api/v1/jobs/{job['id']}/evidence", headers=LEAD).json()
    kinds = {e["kind"] for e in evidence}
    assert {
        "log",
        "environment_manifest",
        "source_inventory",
        "scanner_report",
        "junit_xml",
    } <= kinds
    log = next(e for e in evidence if e["id"] == by_engine["pytest"]["log_evidence_id"])
    content = client.get(f"/api/v1/evidence/{log['id']}/content", headers=LEAD).json()
    assert "failed" in content["text"] and content["sha256"] == log["sha256"]
    raw = client.get(f"/api/v1/evidence/{log['id']}/download", headers=LEAD)
    assert raw.status_code == 200 and raw.headers["X-Content-SHA256"] == log["sha256"]
    assert client.get(f"/api/v1/evidence/{log['id']}", headers=VIEWER).status_code == 403

    runs = client.get(f"/api/v1/jobs/{job['id']}/worker-runs", headers=LEAD).json()
    assert len(runs) == 4 and all(r["destroyed_at"] and r["isolation"] == "process" for r in runs)

    report = client.get(f"/api/v1/jobs/{job['id']}/report", headers=LEAD).json()
    assert report["partial"] is False and report["content"]["summary"]["checks"] == {
        "passed": 2,
        "failed": 2,
    }
    assert report["content"]["verdict"] is None and report["digest"]
    html = client.get(f"/api/v1/jobs/{job['id']}/report?format=html", headers=LEAD)
    assert (
        html.status_code == 200
        and "text/html" in html.headers["content-type"]
        and "QJ-" in html.text
    )
    assert (
        client.get(f"/api/v1/jobs/{job['id']}/report?format=sarif", headers=LEAD).status_code == 501
    )

    audit = client.get(f"/api/v1/audit-events?job_id={job['id']}&limit=200", headers=LEAD).json()
    actions = {a["action"] for a in audit["items"]}
    assert {
        "job.created",
        "source.pinned",
        "job.planned",
        "task.state_changed",
        "worker_run.started",
        "worker_run.destroyed",
        "snapshot.recorded",
        "job.state_changed",
    } <= actions
    assert client.get("/api/v1/audit-events", headers=VIEWER).status_code == 403
    with session_scope() as s:
        assert verify_chain(s, job["org_id"]) is None


def test_second_run_on_fixed_ref_compares_as_improved(
    client: TestClient, settings: Settings, tmp_path: Path
) -> None:
    repo = _repo(client)
    worker = _worker(client, settings, tmp_path, allow=True)
    base = _drive(client, settings, worker, _job(client, repo["id"], "main")["id"])
    other = _drive(client, settings, worker, _job(client, repo["id"], "fix-rounding")["id"])
    assert other["state"] == "completed" and other["check_summary"] == {"passed": 4}
    # the fixed run is the base; its delta is read relative to the earlier (broken) run
    cmp = client.get(f"/api/v1/jobs/{other['id']}/compare?with={base['id']}", headers=LEAD).json()
    assert cmp["same_repository"] is True and cmp["same_commit"] is False
    deltas = {c["engine"]: c["delta"] for c in cmp["checks"]}
    assert deltas["pytest"] == "improved" and deltas["python_syntax"] == "improved"
    assert deltas["snapshot_integrity"] == "unchanged"
    assert cmp["check_deltas"] == {"improved": 2, "unchanged": 2}
    assert cmp["test_deltas"]["improved"] == 2 and all(
        t["delta"] == "improved" for t in cmp["tests"]
    )
    assert cmp["test_counts"]["base"] == {"passed": 7}
    assert (
        client.get(f"/api/v1/jobs/{base['id']}/compare?with={base['id']}", headers=LEAD).status_code
        == 400
    )


# --------------------------------------------------------------- safety paths
def test_code_executing_engine_is_refused_without_opt_in(
    client: TestClient, settings: Settings, tmp_path: Path
) -> None:
    repo = _repo(client)
    final = _drive(
        client,
        settings,
        _worker(client, settings, tmp_path, allow=False),
        _job(client, repo["id"])["id"],
    )
    assert final["state"] == "completed_with_warnings"
    checks = {
        c["engine_id"]: c
        for c in client.get(f"/api/v1/jobs/{final['id']}/checks", headers=LEAD).json()
    }
    assert (
        checks["pytest"]["outcome"] == "skipped"
        and "refused" in checks["pytest"]["failure_message"]
    )
    assert final["test_summary"] == {}
    caps = client.get("/api/v1/system/capabilities", headers=LEAD).json()
    assert caps["execution_enabled"] is True and caps["repository_code_execution_allowed"] is False


def test_intake_failures_block_or_fail_the_job_honestly(
    client: TestClient, settings: Settings
) -> None:
    repo = _repo(client)
    bad_ref = _job(client, repo["id"], ref="does-not-exist")
    run_until_idle(Scheduler(settings))
    j = client.get(f"/api/v1/jobs/{bad_ref['id']}", headers=LEAD).json()
    assert j["state"] == "failed" and j["commit_sha"] is None
    assert client.get(f"/api/v1/jobs/{bad_ref['id']}/tasks", headers=LEAD).json() == []

    # Fixtures disabled → policy denial → blocked, nothing executed.
    strict = Settings(**{**settings.model_dump(), "dev_fixture_repos": False})
    other = _job(client, repo["id"], ref="fix-rounding")
    run_until_idle(Scheduler(strict))
    assert client.get(f"/api/v1/jobs/{other['id']}", headers=LEAD).json()["state"] == "blocked"


def test_invalid_worker_result_fails_attempt_and_retries_within_budget(
    client: TestClient, settings: Settings
) -> None:
    repo = _repo(client)
    job = _job(client, repo["id"])
    run_until_idle(Scheduler(settings))
    cp = ControlPlaneClient(client, TOKEN)
    leased = cp.lease("w-bad", ["env_prepare"])
    assert len(leased) == 1
    task_id = leased[0]["task_id"]
    with pytest.raises(Exception, match="422"):
        cp.submit_result(
            task_id, {"worker_id": "w-bad", "worker_result": {"schema_version": "1.0"}}
        )
    with session_scope() as s:
        t = s.execute(select(Task).where(Task.id == task_id)).scalar_one()
        assert (
            t.state == "retry_scheduled"
            and t.last_error_code == "E-EXEC-004"
            and t.attempt_count == 1
        )
    # Second and third attempts: worker crashes (retryable) → budget exhausted → task failed.
    for n in (2, 3):
        leased = cp.lease("w-bad", ["env_prepare"])
        assert leased and leased[0]["attempt_no"] == n
        cp.submit_failure(
            task_id,
            {
                "worker_id": "w-bad",
                "error_code": "E-EXEC-001",
                "retryable": True,
                "message": "boom",
            },
        )
    with session_scope() as s:
        t = s.execute(select(Task).where(Task.id == task_id)).scalar_one()
        assert t.state == "failed" and t.last_error_class == "infrastructure_error"
    run_until_idle(Scheduler(settings))
    j = client.get(f"/api/v1/jobs/{job['id']}", headers=LEAD).json()
    assert j["state"] == "failed"
    assert j["task_summary"] == {"failed": 1, "skipped": 3}  # dependents skipped, never run
    assert client.get(f"/api/v1/jobs/{job['id']}/report", headers=LEAD).json()["partial"] is True


def test_worker_timeout_is_recorded_as_timed_out_and_not_retried(
    client: TestClient, settings: Settings
) -> None:
    repo = _repo(client)
    job = _job(client, repo["id"])
    run_until_idle(Scheduler(settings))
    cp = ControlPlaneClient(client, TOKEN)
    task_id = cp.lease("w-slow", ["env_prepare"])[0]["task_id"]
    cp.submit_failure(
        task_id,
        {
            "worker_id": "w-slow",
            "error_code": "E-EXEC-007",
            "error_class": "tool_error",
            "retryable": False,
            "kind": "timed_out",
            "message": "wall clock",
        },
    )
    with session_scope() as s:
        assert s.execute(select(Task.state).where(Task.id == task_id)).scalar_one() == "timed_out"
    run_until_idle(Scheduler(settings))
    assert client.get(f"/api/v1/jobs/{job['id']}", headers=LEAD).json()["state"] == "failed"


def test_cancel_with_a_live_worker_waits_for_destruction(
    client: TestClient, settings: Settings, tmp_path: Path
) -> None:
    repo = _repo(client)
    job = _job(client, repo["id"])
    run_until_idle(Scheduler(settings))
    cp = ControlPlaneClient(client, TOKEN)
    leased = cp.lease("w-live", ["env_prepare"])[0]
    run_id = cp.create_worker_run(
        leased["task_id"],
        {
            "worker_id": "w-live",
            "runtime": "subprocess",
            "isolation": "process",
            "image_digest": "sha256:" + "b" * 32,
        },
    )
    cancel = client.post(f"/api/v1/jobs/{job['id']}/cancel", json={"reason": "stop"}, headers=LEAD)
    assert cancel.status_code == 202 and cancel.json()["state"] == "cancelling"
    with pytest.raises(LeaseLostError):
        cp.heartbeat(leased["task_id"], "w-live")
    run_until_idle(Scheduler(settings))
    assert client.get(f"/api/v1/jobs/{job['id']}", headers=LEAD).json()["state"] == "cancelling"
    cp.destroy_worker_run(run_id, {"outcome": "cancelled"})
    run_until_idle(Scheduler(settings))
    final = client.get(f"/api/v1/jobs/{job['id']}", headers=LEAD).json()
    assert final["state"] == "cancelled"
    with session_scope() as s:
        assert (
            s.execute(select(WorkerRun.destroyed_at).where(WorkerRun.id == run_id)).scalar_one()
            is not None
        )


def test_worker_process_discards_result_after_lease_loss(
    client: TestClient, settings: Settings, tmp_path: Path
) -> None:
    repo = _repo(client)
    job = _job(client, repo["id"])
    run_until_idle(Scheduler(settings))
    worker = _worker(client, settings, tmp_path, allow=False, worker_id="w-proc")
    leased = worker.client.lease("w-proc", ["env_prepare"])[0]
    TaskQueue(settings)  # queue semantics are exercised through the API below
    client.post(f"/api/v1/jobs/{job['id']}/cancel", headers=LEAD)
    worker.process(leased)  # must not raise; the result is discarded and the run destroyed
    with session_scope() as s:
        runs = (
            s.execute(select(WorkerRun).where(WorkerRun.task_id == leased["task_id"]))
            .scalars()
            .all()
        )
        # The lease was lost before a run started, so no run leaks; any run that did start is destroyed.
        assert all(r.destroyed_at is not None for r in runs)
    run_until_idle(Scheduler(settings))
    assert client.get(f"/api/v1/jobs/{job['id']}", headers=LEAD).json()["state"] == "cancelled"


def test_exec_internal_api_requires_the_token(
    client: TestClient, settings: Settings, clean_db: Engine
) -> None:
    body = {"worker_id": "x", "task_types": ["check"]}
    assert client.post("/internal/v1/exec/lease", json=body).status_code == 401
    assert (
        client.post(
            "/internal/v1/exec/lease", json=body, headers={"X-Exec-Token": "wrong"}
        ).status_code
        == 401
    )
    ok = client.post("/internal/v1/exec/lease", json=body, headers={"X-Exec-Token": TOKEN})
    assert ok.status_code == 200 and ok.json() == {"tasks": []}
    disabled = create_app(Settings(**{**settings.model_dump(), "exec_token": None}))
    disabled.dependency_overrides[get_settings] = lambda: Settings(
        **{**settings.model_dump(), "exec_token": None}
    )
    with TestClient(disabled, raise_server_exceptions=False) as c:
        assert (
            c.post(
                "/internal/v1/exec/lease", json=body, headers={"X-Exec-Token": TOKEN}
            ).status_code
            == 503
        )


def test_job_deadline_times_out_running_jobs(client: TestClient, settings: Settings) -> None:
    from datetime import UTC, datetime, timedelta

    from qaswarm.db.models import Job

    repo = _repo(client)
    job = _job(client, repo["id"])
    run_until_idle(Scheduler(settings))
    with session_scope() as s:
        j = s.execute(select(Job).where(Job.id == job["id"])).scalar_one()
        assert j.state == "running"
        j.deadline_at = datetime.now(UTC) - timedelta(seconds=1)
    run_until_idle(Scheduler(settings))
    final = client.get(f"/api/v1/jobs/{job['id']}", headers=LEAD).json()
    assert final["state"] == "timed_out" and final["task_summary"] == {"cancelled": 4}
