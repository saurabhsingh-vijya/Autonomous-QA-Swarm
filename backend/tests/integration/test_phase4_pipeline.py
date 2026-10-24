"""Phase 4 integration tests against PostgreSQL with an in-process Execution Service worker.

Covers the targets API (FR-050 / HA-01), policy refusal before any worker starts (AC-149), a full
pipeline with API, browser, security and performance checks against the worker-started local
fixture target, a blocked registered target end to end, and the regression rerun + compare flow.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from qaswarm_exec.host.client import ControlPlaneClient
from qaswarm_exec.host.worker import ExecWorker
from qaswarm_exec.runtime.subprocess_runtime import SubprocessRuntime
from qaswarm_exec.tools.browser_tests import playwright_status
from sqlalchemy import Engine

from qaswarm.api.app import create_app
from qaswarm.config import Settings, get_settings
from qaswarm.workflow.scheduler import Scheduler, run_until_idle

pytestmark = pytest.mark.integration

FIXTURES = str(Path(__file__).resolve().parents[3] / "exec" / "fixtures")
TOKEN = "test-exec-token"
ADMIN = {"X-Dev-User": "usr_admin", "X-Dev-Role": "Org Admin"}
LEAD = {"X-Dev-User": "usr_lead", "X-Dev-Role": "QA Lead"}
ENGINEER = {"X-Dev-User": "usr_eng", "X-Dev-Role": "QA Engineer"}
REVIEWER = {"X-Dev-User": "usr_sec", "X-Dev-Role": "Security Reviewer"}
TERMINAL = {"completed", "completed_with_warnings", "failed", "cancelled", "timed_out", "blocked"}


def _settings(tmp_path: Path, test_settings: Settings, **over: Any) -> Settings:
    base: dict[str, Any] = {
        "database_url": test_settings.database_url,
        "dev_auth": True,
        "exec_token": TOKEN,
        "evidence_dir": str(tmp_path / "evidence"),
        "dev_fixture_repos": True,
        "fixtures_dir": FIXTURES,
        "intake_dns_check": False,
        "backoff_seconds": [0, 0],
        "backoff_jitter": 0.0,
        "lease_ttl_seconds": 90,
        "task_wall_clock_seconds": 300,
        "sse_heartbeat_seconds": 1,
    }
    base.update(over)
    return Settings(**base)


@pytest.fixture
def settings(tmp_path: Path, test_settings: Settings) -> Settings:
    return _settings(tmp_path, test_settings)


@pytest.fixture
def client(clean_db: Engine, settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _worker(
    client: TestClient, settings: Settings, tmp_path: Path, *, allow_local: bool = False
) -> ExecWorker:
    return ExecWorker(
        ControlPlaneClient(client, TOKEN),
        SubprocessRuntime(),
        worker_id="w-p4",
        workspace_root=tmp_path / "ws",
        allow_code_execution=False,
        fixtures_dir=settings.fixtures_dir,
        heartbeat_seconds=60,
        engine_settings={"allow_local_targets": allow_local},
    )


def _project_and_repo(client: TestClient, name: str = "sample-web-app") -> tuple[str, str]:
    project = client.post(
        "/api/v1/projects", json={"name": f"P4-{uuid.uuid4().hex[:6]}"}, headers=LEAD
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
    return project["id"], r.json()["id"]


def _job(client: TestClient, repo_id: str, **body: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"repository_id": repo_id, "ref": "main", **body}
    r = client.post(
        "/api/v1/jobs", json=payload, headers={**LEAD, "Idempotency-Key": uuid.uuid4().hex}
    )
    assert r.status_code == 202, r.text
    return r.json()


def _drive(
    client: TestClient, settings: Settings, worker: ExecWorker, job_id: str, *, max_rounds: int = 40
) -> dict[str, Any]:
    scheduler = Scheduler(settings)
    for _ in range(max_rounds):
        run_until_idle(scheduler, max_ticks=10)
        while worker.run_once():
            pass
        run_until_idle(scheduler, max_ticks=10)
        job = client.get(f"/api/v1/jobs/{job_id}", headers=LEAD).json()
        if job["state"] in TERMINAL:
            return job
    raise AssertionError(f"job did not finish: {job}")


def _register_target(
    client: TestClient, project_id: str, base_url: str = "https://staging.example.test"
) -> dict[str, Any]:
    r = client.post(
        "/api/v1/targets",
        json={
            "project_id": project_id,
            "name": f"staging-{uuid.uuid4().hex[:4]}",
            "environment_type": "staging",
            "base_url": base_url,
            "owner": "platform-team@example.test",
        },
        headers=ADMIN,
    )
    assert r.status_code == 201, r.text
    return r.json()


def _authorize(
    client: TestClient, target_id: str, activities: list[str], days: int = 7
) -> dict[str, Any]:
    r = client.post(
        f"/api/v1/targets/{target_id}/authorizations",
        json={
            "allowed_activities": activities,
            "valid_until": (datetime.now(UTC) + timedelta(days=days)).isoformat(),
            "note": "integration test attestation",
        },
        headers=REVIEWER,
    )
    assert r.status_code == 201, r.text
    return r.json()


# ------------------------------------------------------------------ targets API
def test_targets_api_roles_validation_and_attestations(client: TestClient) -> None:
    project_id, _ = _project_and_repo(client)
    body = {
        "project_id": project_id,
        "name": "staging",
        "environment_type": "staging",
        "base_url": "https://staging.example.test",
        "owner": "owner@example.test",
    }
    assert client.post("/api/v1/targets", json=body, headers=LEAD).status_code == 403
    private = client.post(
        "/api/v1/targets", json={**body, "base_url": "http://10.0.0.8"}, headers=ADMIN
    )
    assert private.status_code == 422 and private.json()["error_code"] == "target_host_not_allowed"
    missing = client.post("/api/v1/targets", json={**body, "owner": ""}, headers=ADMIN)
    assert missing.status_code == 422  # AC-148: owner is required
    created = client.post("/api/v1/targets", json=body, headers=ADMIN)
    assert created.status_code == 201 and created.headers["Location"].endswith(created.json()["id"])
    target = created.json()
    assert target["active_authorization"] is None and target["kind"] == "registered"
    assert client.post("/api/v1/targets", json=body, headers=ADMIN).status_code == 409

    # AC-149: only Org Admin or Security Reviewer may attest.
    auth_body = {
        "allowed_activities": ["api"],
        "valid_until": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
    }
    assert (
        client.post(
            f"/api/v1/targets/{target['id']}/authorizations", json=auth_body, headers=ENGINEER
        ).status_code
        == 403
    )
    past = client.post(
        f"/api/v1/targets/{target['id']}/authorizations",
        json={**auth_body, "valid_until": (datetime.now(UTC) - timedelta(days=1)).isoformat()},
        headers=REVIEWER,
    )
    assert past.status_code == 422
    auth = _authorize(client, target["id"], ["api"])
    assert auth["active"] and auth["attested_role"] == "Security Reviewer"
    listed = client.get(f"/api/v1/targets?project_id={project_id}", headers=ENGINEER).json()
    assert listed[0]["active_authorization"]["id"] == auth["id"]
    # A new attestation for an overlapping activity supersedes the old one.
    auth2 = _authorize(client, target["id"], ["api", "security"])
    detail = client.get(f"/api/v1/targets/{target['id']}", headers=ENGINEER).json()
    assert detail["active_authorization"]["id"] == auth2["id"]
    assert (
        client.delete(
            f"/api/v1/targets/{target['id']}/authorizations/{auth2['id']}", headers=REVIEWER
        ).status_code
        == 204
    )
    assert (
        client.get(f"/api/v1/targets/{target['id']}", headers=ENGINEER).json()[
            "active_authorization"
        ]
        is None
    )
    events = client.get("/api/v1/audit-events?action=target.authorized", headers=LEAD).json()
    assert len(events["items"]) == 2 and events["items"][0]["details"]["approval"] == "HA-01"


# ------------------------------------------------------- policy refusal (AC-149)
def test_job_with_unauthorized_target_is_blocked_with_zero_worker_runs(
    client: TestClient, settings: Settings, tmp_path: Path
) -> None:
    project_id, repo_id = _project_and_repo(client)
    target = _register_target(client, project_id)
    other_project, _ = _project_and_repo(client, name="sample-python-app")
    wrong = client.post(
        "/api/v1/jobs",
        json={
            "repository_id": repo_id,
            "ref": "main",
            "target_id": _register_target(client, other_project)["id"],
        },
        headers={**LEAD, "Idempotency-Key": uuid.uuid4().hex},
    )
    assert wrong.status_code == 422 and wrong.json()["errors"][0]["code"] == "project_mismatch"

    job = _job(client, repo_id, target_id=target["id"], testing={"api": {}})
    final = _drive(client, settings, _worker(client, settings, tmp_path), job["id"])
    assert final["state"] == "blocked" and final["task_summary"] == {}
    assert any("HA-01" in w for w in final["warnings"])
    assert client.get(f"/api/v1/jobs/{job['id']}/worker-runs", headers=LEAD).json() == []

    # Authorised for api only, but the job also asks for security → still blocked, reason named.
    _authorize(client, target["id"], ["api"])
    job2 = _job(
        client,
        repo_id,
        target_id=target["id"],
        profiles={"functional": "none", "security": "quick", "performance": "none"},
        testing={"api": {}},
    )
    final2 = _drive(client, settings, _worker(client, settings, tmp_path), job2["id"])
    assert final2["state"] == "blocked"
    assert any("activities_not_authorized:security" in w for w in final2["warnings"])
    audit = client.get(f"/api/v1/audit-events?job_id={job2['id']}", headers=LEAD).json()
    assert any(e["details"].get("approval") == "HA-01" for e in audit["items"])


# ------------------------------------------------------ full pipeline + rerun
def test_full_pipeline_with_target_engines_and_regression_rerun(
    client: TestClient, settings: Settings, tmp_path: Path
) -> None:
    _, repo_id = _project_and_repo(client)
    testing = {
        "target": "local_fixture",
        "api": {},
        "browser": {},
        "security": {"paths": ["/", "/login", "/boom", "/redirect-private"]},
        "performance": {"max_requests": 12, "concurrency": 2, "paths": ["/health"]},
    }
    job = _job(
        client,
        repo_id,
        profiles={"functional": "standard", "security": "standard", "performance": "smoke"},
        testing=testing,
    )
    assert job["inputs"]["testing"]["target"] == "local_fixture"
    worker = _worker(client, settings, tmp_path)
    final = _drive(client, settings, worker, job["id"])
    assert final["state"] in {"completed", "completed_with_warnings"}, final
    checks = {
        c["engine_id"]: c
        for c in client.get(f"/api/v1/jobs/{job['id']}/checks", headers=LEAD).json()
    }
    assert set(checks) == {
        "env_prepare",
        "snapshot_integrity",
        "python_syntax",
        "pytest",
        "secret_scan",
        "api_tests",
        "browser_tests",
        "security_checks",
        "performance_probe",
    }
    assert checks["api_tests"]["outcome"] == "passed", checks["api_tests"]["failure_message"]
    assert checks["api_tests"]["summary"]["steps"] == 5
    assert checks["security_checks"]["outcome"] == "failed"
    assert checks["security_checks"]["summary"]["high"] == 1
    assert checks["performance_probe"]["outcome"] == "passed"
    assert checks["performance_probe"]["summary"]["requests"] == 12
    assert all(
        c["executes_repository_code"] is False
        for c in checks.values()
        if c["engine_id"] != "pytest"
    )
    if playwright_status()[0]:
        assert checks["browser_tests"]["outcome"] == "passed", checks["browser_tests"][
            "failure_message"
        ]
    else:
        assert checks["browser_tests"]["outcome"] == "skipped"
    stages = {s["stage"]: s["status"] for s in final["stages"]}
    assert (
        stages["performance_testing"] == "succeeded" and stages["security_testing"] == "succeeded"
    )

    tests = client.get(f"/api/v1/jobs/{job['id']}/test-executions?limit=200", headers=LEAD).json()
    node_ids = {t["node_id"] for t in tests["items"]}
    assert "items-api::create and fetch an item::fetch created item" in node_ids
    assert "security::verbose_error_body::/boom" in node_ids and "perf::/health" in node_ids

    evidence = client.get(f"/api/v1/jobs/{job['id']}/evidence", headers=LEAD).json()
    kinds = {e["kind"] for e in evidence}
    assert {"api_test_report", "security_report", "performance_report", "log"} <= kinds
    if playwright_status()[0]:
        assert {"screenshot", "browser_console", "browser_test_report"} <= kinds
        shot = next(e for e in evidence if e["kind"] == "screenshot")
        assert shot["media_type"] == "image/png" and shot["deterministic"] is False
        png = client.get(f"/api/v1/evidence/{shot['id']}/download", headers=LEAD)
        assert png.status_code == 200 and png.content[:4] == b"\x89PNG"
    sec = next(e for e in evidence if e["kind"] == "security_report")
    content = client.get(f"/api/v1/evidence/{sec['id']}/content", headers=LEAD).json()
    assert "certification" in content["text"] and "csrf=" not in content["text"]

    # Rerun only two engines → new job, restricted plan, compare link works.
    bad = client.post(f"/api/v1/jobs/{job['id']}/rerun", json={"engines": ["nope"]}, headers=LEAD)
    assert bad.status_code == 422
    rerun = client.post(
        f"/api/v1/jobs/{job['id']}/rerun",
        json={"engines": ["api_tests", "security_checks"], "reason": "regression check"},
        headers=LEAD,
    )
    assert rerun.status_code == 202, rerun.text
    new = rerun.json()
    assert new["id"] != job["id"]
    assert new["links"]["compare"] == f"/api/v1/jobs/{job['id']}/compare?with={new['id']}"
    assert new["inputs"]["rerun"]["of_job"] == job["id"]
    busy = client.post(
        f"/api/v1/jobs/{new['id']}/rerun", json={"engines": ["api_tests"]}, headers=LEAD
    )
    assert busy.status_code == 409
    final2 = _drive(client, settings, worker, new["id"])
    assert final2["state"] in {"completed", "completed_with_warnings"}, final2
    engines2 = {
        c["engine_id"] for c in client.get(f"/api/v1/jobs/{new['id']}/checks", headers=LEAD).json()
    }
    assert engines2 == {"env_prepare", "api_tests", "security_checks"}
    compare = client.get(new["links"]["compare"], headers=LEAD)
    assert compare.status_code == 200
    body = compare.json()
    deltas = {c["engine"]: c["delta"] for c in body["checks"]}
    assert deltas["api_tests"] == "unchanged" and deltas["security_checks"] == "unchanged"
    assert deltas["performance_probe"] == "removed" and body["same_commit"] is True
    assert body["test_deltas"].get("regressed", 0) == 0


# ---------------------------------------------------- blocked target, end to end
def test_registered_loopback_target_is_refused_by_the_worker_unless_local_mode(
    clean_db: Engine, test_settings: Settings, tmp_path: Path
) -> None:
    settings = _settings(tmp_path, test_settings, allow_local_targets=True)
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app, raise_server_exceptions=False) as client:
        project_id, repo_id = _project_and_repo(client)
        target = _register_target(client, project_id, base_url="http://127.0.0.1:9")
        _authorize(client, target["id"], ["api", "security"])
        job = _job(
            client,
            repo_id,
            target_id=target["id"],
            profiles={"functional": "none", "security": "quick", "performance": "none"},
            testing={"api": {}},
        )
        final = _drive(client, settings, _worker(client, settings, tmp_path), job["id"])
        assert final["state"] in {"completed", "completed_with_warnings"}
        checks = {
            c["engine_id"]: c
            for c in client.get(f"/api/v1/jobs/{job['id']}/checks", headers=LEAD).json()
        }
        assert (
            checks["api_tests"]["outcome"] == "skipped"
            and checks["api_tests"]["summary"]["blocked"]
        )
        assert checks["api_tests"]["summary"]["reason"] == "private_address"
        assert "AQS_EXEC_ALLOW_LOCAL_TARGETS" in checks["api_tests"]["failure_message"]
        assert checks["security_checks"]["outcome"] == "skipped"
        blocked_tests = client.get(
            f"/api/v1/jobs/{job['id']}/test-executions?status=blocked", headers=LEAD
        ).json()
        assert len(blocked_tests["items"]) == 5  # every planned API step is reported as blocked
        # Even in local mode the port is closed: the engine reports transport failures, not a pass.
        job2 = _job(client, repo_id, target_id=target["id"], testing={"api": {}}, force_new=True)
        final2 = _drive(
            client, settings, _worker(client, settings, tmp_path, allow_local=True), job2["id"]
        )
        checks2 = {
            c["engine_id"]: c
            for c in client.get(f"/api/v1/jobs/{job2['id']}/checks", headers=LEAD).json()
        }
        assert checks2["api_tests"]["outcome"] == "failed"
        assert "transport error" in checks2["api_tests"]["failure_message"]
