"""End-to-end API behaviour against PostgreSQL."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from qaswarm.api.services.jobs import HELD_REASON
from qaswarm.audit.chain import verify_chain
from qaswarm.db.models import AuditEvent
from qaswarm.db.session import session_scope

pytestmark = pytest.mark.integration


def _project(client: TestClient, headers: dict[str, str], name: str = "Checkout") -> dict:
    r = client.post("/api/v1/projects", json={"name": name, "description": "d"}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def _repo(
    client: TestClient,
    headers: dict[str, str],
    project_id: str,
    url: str = "https://github.com/northwind/payments-api",
) -> dict:
    r = client.post(
        "/api/v1/repositories",
        headers=headers,
        json={"project_id": project_id, "provider": "github", "url": url},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _job(
    client: TestClient,
    headers: dict[str, str],
    repo_id: str,
    key: str | None = None,
    **extra: object,
):
    h = {**headers, "Idempotency-Key": key or uuid.uuid4().hex}
    body = {
        "repository_id": repo_id,
        "ref": "main",
        "profiles": {"functional": "standard", "security": "quick", "performance": "none"},
        **extra,
    }
    return client.post("/api/v1/jobs", json=body, headers=h)


def test_health_and_readiness(client: TestClient) -> None:
    assert client.get("/healthz").json()["status"] == "ok"
    r = client.get("/readyz")
    assert r.status_code == 200 and r.json()["database"] == "reachable"


def test_seeded_sample_project_is_listed_and_labelled(
    client: TestClient, auth_headers: dict
) -> None:
    r = client.get("/api/v1/projects", headers=auth_headers)
    assert r.status_code == 200
    items = r.json()["items"]
    assert any(p["name"] == "Payments Platform" and p["is_sample"] for p in items)
    assert items[0]["org_name"] == "Northwind Fintech (sample org)"


def test_project_crud_and_persistence(
    client: TestClient, auth_headers: dict, viewer_headers: dict
) -> None:
    created = _project(client, auth_headers)
    pid = created["id"]
    assert pid.startswith("prj_") and created["version"] == 1

    got = client.get(f"/api/v1/projects/{pid}", headers=auth_headers)
    assert got.status_code == 200 and got.headers["ETag"] == f'"{pid}:v1"'

    dup = client.post("/api/v1/projects", json={"name": "Checkout"}, headers=auth_headers)
    assert dup.status_code == 409 and dup.json()["error_code"] == "project_name_taken"

    upd = client.patch(
        f"/api/v1/projects/{pid}",
        json={"name": "Checkout v2"},
        headers={**auth_headers, "If-Match": f'"{pid}:v1"'},
    )
    assert (
        upd.status_code == 200
        and upd.json()["name"] == "Checkout v2"
        and upd.json()["version"] == 2
    )

    stale = client.patch(
        f"/api/v1/projects/{pid}",
        json={"name": "x"},
        headers={**auth_headers, "If-Match": f'"{pid}:v1"'},
    )
    assert stale.status_code == 412 and stale.json()["error_code"] == "etag_mismatch"

    forbidden = client.patch(f"/api/v1/projects/{pid}", json={"name": "x"}, headers=viewer_headers)
    assert forbidden.status_code == 403 and forbidden.json()["error_code"] == "insufficient_role"

    # Data survives a fresh app instance (new TestClient against the same database).
    from qaswarm.api.app import create_app

    with TestClient(create_app(client.app.state.settings)) as fresh:
        assert (
            fresh.get(f"/api/v1/projects/{pid}", headers=auth_headers).json()["name"]
            == "Checkout v2"
        )

    assert client.delete(f"/api/v1/projects/{pid}", headers=auth_headers).status_code == 204
    assert client.get(f"/api/v1/projects/{pid}", headers=auth_headers).status_code == 404
    names = [
        p["name"] for p in client.get("/api/v1/projects", headers=auth_headers).json()["items"]
    ]
    assert "Checkout v2" not in names


def test_validation_errors_are_problem_json_with_pointers(
    client: TestClient, auth_headers: dict
) -> None:
    r = client.post("/api/v1/projects", json={"name": "", "bogus": 1}, headers=auth_headers)
    assert r.status_code == 422
    body = r.json()
    assert body["error_code"] == "validation_failed"
    pointers = {e["pointer"] for e in body["errors"]}
    assert "/name" in pointers and "/bogus" in pointers


def test_repository_registration_and_syntactic_rejection(
    client: TestClient, auth_headers: dict
) -> None:
    project = _project(client, auth_headers)
    repo = _repo(client, auth_headers, project["id"])
    assert repo["validation_status"] == "pending_validation"
    assert "No code was fetched" in repo["validation_note"]
    assert (
        client.get(f"/api/v1/repositories/{repo['id']}", headers=auth_headers).json()["id"]
        == repo["id"]
    )

    r = client.post(
        "/api/v1/repositories",
        headers=auth_headers,
        json={
            "project_id": project["id"],
            "provider": "github",
            "url": "http://10.0.4.12/internal/repo.git",
        },
    )
    assert r.status_code == 422
    body = r.json()
    assert body["error_code"] == "repository_url_rejected" and body["reason"] == "scheme_not_https"
    assert body["errors"][0]["pointer"] == "/url"

    again = client.post(
        "/api/v1/repositories",
        headers=auth_headers,
        json={
            "project_id": project["id"],
            "provider": "github",
            "url": "https://github.com/Northwind/payments-api.git",
        },
    )
    assert again.status_code == 409 and again.json()["error_code"] == "repository_exists"

    listed = client.get(
        f"/api/v1/repositories?project_id={project['id']}", headers=auth_headers
    ).json()
    assert [x["id"] for x in listed["items"]] == [repo["id"]]


def test_job_creation_is_honest_idempotent_and_duplicate_safe(
    client: TestClient, auth_headers: dict, engineer_headers: dict
) -> None:
    project = _project(client, auth_headers)
    repo = _repo(client, auth_headers, project["id"])

    missing = client.post(
        "/api/v1/jobs", json={"repository_id": repo["id"], "ref": "main"}, headers=auth_headers
    )
    assert missing.status_code == 400 and missing.json()["error_code"] == "idempotency_key_required"

    key = "ci-run-1"
    first = _job(client, auth_headers, repo["id"], key)
    assert first.status_code == 202, first.text
    job = first.json()
    assert job["state"] == "validating" and job["held_reason"] == HELD_REASON
    assert job["display_id"].startswith("QJ-") and job["commit_sha"] is None
    assert job["project_id"] == project["id"]
    assert first.headers["Location"] == f"/api/v1/jobs/{job['id']}"

    replay = _job(client, auth_headers, repo["id"], key)
    assert replay.status_code == 202 and replay.json() == job
    assert replay.headers["Idempotent-Replayed"] == "true"

    reused = client.post(
        "/api/v1/jobs",
        json={"repository_id": repo["id"], "ref": "other"},
        headers={**auth_headers, "Idempotency-Key": key},
    )
    assert reused.status_code == 422 and reused.json()["error_code"] == "idempotency_key_reused"

    dup = _job(client, auth_headers, repo["id"])
    assert dup.status_code == 409
    assert dup.json()["error_code"] == "job_duplicate_active"
    assert dup.json()["existing_job"]["id"] == job["id"]

    not_lead = _job(client, engineer_headers, repo["id"], force_new=True)
    assert not_lead.status_code == 403

    forced = _job(client, auth_headers, repo["id"], force_new=True)
    assert forced.status_code == 202 and forced.json()["id"] != job["id"]

    listing = client.get(
        f"/api/v1/jobs?project_id={project['id']}&state=validating", headers=auth_headers
    )
    assert {j["id"] for j in listing.json()["items"]} == {job["id"], forced.json()["id"]}
    bad_filter = client.get("/api/v1/jobs?state=flying", headers=auth_headers)
    assert bad_filter.status_code == 400 and bad_filter.json()["error_code"] == "unsupported_filter"

    detail = client.get(f"/api/v1/jobs/{job['id']}", headers=auth_headers)
    assert detail.status_code == 200
    stages = detail.json()["stages"]
    assert len(stages) == 13 and stages[0]["status"] == "held"
    assert all(s["status"] == "pending" for s in stages[1:])

    # Audit chain records creation and the state change, and verifies.
    with session_scope() as session:
        actions = (
            session.execute(
                select(AuditEvent.action)
                .where(AuditEvent.job_id == job["id"])
                .order_by(AuditEvent.seq)
            )
            .scalars()
            .all()
        )
        assert actions == ["job.created", "job.state_changed", "job.held"]
        assert verify_chain(session, job["org_id"]) is None


def test_cancel_goes_through_state_machine(client: TestClient, auth_headers: dict) -> None:
    project = _project(client, auth_headers)
    repo = _repo(client, auth_headers, project["id"])
    job = _job(client, auth_headers, repo["id"]).json()

    r = client.post(
        f"/api/v1/jobs/{job['id']}/cancel", json={"reason": "superseded"}, headers=auth_headers
    )
    assert r.status_code == 202 and r.json()["state"] == "cancelled"
    detail = client.get(f"/api/v1/jobs/{job['id']}", headers=auth_headers).json()
    assert detail["state"] == "cancelled" and detail["cancel_reason"] == "superseded"
    assert detail["ended_at"] is not None and detail["held_reason"] is None

    again = client.post(f"/api/v1/jobs/{job['id']}/cancel", headers=auth_headers)
    assert again.status_code == 409 and again.json()["error_code"] == "invalid_state_transition"

    with session_scope() as session:
        transitions = (
            session.execute(
                select(AuditEvent.details)
                .where(AuditEvent.job_id == job["id"], AuditEvent.action == "job.state_changed")
                .order_by(AuditEvent.seq)
            )
            .scalars()
            .all()
        )
        assert [t["to"] for t in transitions] == ["validating", "cancelling", "cancelled"]


def test_sse_stream_replays_events_and_ends_on_terminal(
    client: TestClient, auth_headers: dict
) -> None:
    from qaswarm.api.services.jobs import job_event_stream

    project = _project(client, auth_headers)
    repo = _repo(client, auth_headers, project["id"])
    job = _job(client, auth_headers, repo["id"]).json()
    client.post(f"/api/v1/jobs/{job['id']}/cancel", headers=auth_headers)

    frames = list(
        job_event_stream(
            job["id"],
            job["org_id"],
            last_event_id=None,
            heartbeat_seconds=15,
            poll_seconds=0.01,
            max_seconds=5,
        )
    )
    text = "".join(frames)
    assert "event: job.state_changed" in text and text.rstrip().endswith("}")
    assert frames[-1].startswith("id: ") and "event: stream.end" in frames[-1]
    ids = [int(f.split("\n", 1)[0].removeprefix("id: ")) for f in frames]
    assert ids == sorted(ids)

    # Resume after the first event delivers only later events.
    resumed = list(
        job_event_stream(
            job["id"],
            job["org_id"],
            last_event_id=str(ids[0]),
            heartbeat_seconds=15,
            poll_seconds=0.01,
            max_seconds=5,
        )
    )
    assert len(resumed) == len(frames) - 1

    # The HTTP endpoint accepts dev auth via query params (EventSource cannot send headers).
    with client.stream(
        "GET", f"/api/v1/jobs/{job['id']}/events?dev_user=u&dev_role=QA%20Lead"
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        first_chunk = next(resp.iter_text())
        assert "event: " in first_chunk


def test_every_unimplemented_contract_endpoint_returns_501(
    client: TestClient, auth_headers: dict
) -> None:
    from qaswarm.api.contract_table import unimplemented

    for ep in unimplemented():
        path = ep.path.format(
            repository_id="rep_x",
            target_id="tgt_x",
            job_id="job_x",
            finding_id="fnd_x",
            patch_id="pch_x",
            verification_id="ver_x",
        )
        r = client.request(
            ep.method,
            f"/api/v1{path}",
            headers=auth_headers,
            json={} if ep.method == "POST" else None,
        )
        assert r.status_code == 501, (ep, r.text)
        assert r.json()["error_code"] == "not_implemented" and r.json()["planned_slice"] == ep.slice


def test_system_capabilities_are_honest_and_secret_free(
    client: TestClient, auth_headers: dict
) -> None:
    r = client.get("/api/v1/system/capabilities", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["product"] == "RaOne" and body["local_only"] is True
    assert body["database"]["available"] is True
    assert body["execution_service"]["available"] is False
    assert body["execution_service"]["planned_slice"] == "1c"
    assert body["test_engines"] == []
    # The database URL (with its password) is never echoed; the startup warning may name the
    # public sample password so operators know to replace it.
    assert "qaswarm-dev-only@" not in r.text and "password" not in body["storage"]
