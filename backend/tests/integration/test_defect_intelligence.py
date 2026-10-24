"""Phase 5 against PostgreSQL: a real failing check becomes a persisted defect record with
evidence; the same defect is linked across subsequent runs; triage is role-checked, audited and
ETag-protected; suppression carries over; patches stay honestly unimplemented."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from qaswarm.agents.api_testing import HttpChecker
from qaswarm.audit.chain import verify_chain
from qaswarm.config import Settings
from qaswarm.db.models import AuditEvent, Finding
from qaswarm.db.session import session_factory
from qaswarm.workflow.orchestrator import Orchestrator

pytestmark = pytest.mark.integration


def _transport(method: str, url: str) -> tuple[int, dict[str, str], str]:
    if url.endswith("/ok"):
        return 200, {"content-type": "application/json"}, '{"ok":true}'
    return 404, {"content-type": "text/html"}, "<h1>Not Found</h1>"


def _orch(settings: Settings) -> Orchestrator:
    return Orchestrator.from_settings(settings, http=HttpChecker(transport=_transport))


def _repo(client: TestClient, headers: dict) -> str:
    p = client.post(
        "/api/v1/projects", json={"name": f"P5-{uuid.uuid4().hex[:6]}"}, headers=headers
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


def _run(client: TestClient, headers: dict, repo: str, settings: Settings, ref: str) -> dict:
    body = {
        "repository_id": repo,
        "ref": ref,
        "profiles": {"functional": "standard", "security": "none", "performance": "none"},
        "inputs": {
            "requirements": ["The statements endpoint must exist"],
            "api_checks": [
                {"method": "GET", "url": "http://localhost:8000/ok", "expected_status": 200},
                {
                    "method": "GET",
                    "url": "http://localhost:8000/statements",
                    "expected_status": 200,
                    "priority": "P0",
                },
            ],
        },
    }
    r = client.post(
        "/api/v1/jobs", json=body, headers={**headers, "Idempotency-Key": uuid.uuid4().hex}
    )
    assert r.status_code == 202, r.text
    job = r.json()
    with session_factory()() as s:
        done = _orch(settings).run_job_to_completion(s, job["id"])
        assert done.state == "completed_with_warnings"
    return job


def _findings(client: TestClient, headers: dict, job_id: str, **params: str) -> list[dict]:
    r = client.get(f"/api/v1/jobs/{job_id}/findings", params=params, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["items"]


def test_failing_check_produces_defect_record_with_evidence_and_links_across_runs(
    client: TestClient, auth_headers: dict, test_settings: Settings
) -> None:
    repo = _repo(client, auth_headers)
    job1 = _run(client, auth_headers, repo, test_settings, "run-1")
    f1 = _findings(client, auth_headers, job1["id"])
    assert len(f1) == 1
    d = f1[0]
    # Defect record: title, description, severity, affected test, reproducibility, evidence.
    assert d["title"].endswith("observed 404") and "does not discard" in d["description"]
    assert d["severity"] == "medium" and d["status"] == "candidate"
    assert (
        d["affected_tests"]["items"][0]["name"]
        == "GET http://localhost:8000/statements responds 200"
    )
    assert d["reproducibility"]["attempted"] is False and "slice 2b" in d["reproducibility"]["note"]
    assert d["evidence_ids"]["items"] and d["test_execution_ids"]["items"]
    ev = client.get(f"/api/v1/findings/{d['id']}/evidence", headers=auth_headers).json()["items"]
    assert ev[0]["content"]["response"]["status"] == 404 and len(ev[0]["sha256"]) == 64
    # Confirmed observations vs inferred root causes are separate and labelled.
    assert d["facts"]["items"][0].startswith("Observed HTTP 404")
    hyps = d["root_causes"]["items"]
    assert hyps and all(h["verified"] is False and h["uncertainty"] for h in hyps)
    assert any("static or proxy" in h["hypothesis"] for h in hyps)  # text/html body evidence
    assert hyps[0]["supporting_evidence"] == d["evidence_ids"]["items"]
    # Explainable prioritisation.
    assert d["risk_priority"] == 2.4 and d["priority_breakdown"]["severity_weight"] == 4
    assert d["history"]["recurring"] is False and d["history"]["times_seen_before"] == 0
    assert d["status_history"]["items"][0]["action"] == "created"
    # ETag on read.
    r = client.get(f"/api/v1/findings/{d['id']}", headers=auth_headers)
    assert r.headers["ETag"] == f'"{d["id"]}:v1"'

    # Subsequent run on the same repository: same fingerprint, linked history.
    job2 = _run(client, auth_headers, repo, test_settings, "run-2")
    d2 = _findings(client, auth_headers, job2["id"])[0]
    assert d2["fingerprint"] == d["fingerprint"] and d2["id"] != d["id"]
    assert d2["history"]["recurring"] is True and d2["history"]["times_seen_before"] == 1
    assert d2["history"]["prior_occurrences"][0]["finding_id"] == d["id"]
    assert d2["history"]["first_seen"]["job_display_id"] == job1["display_id"]
    assert any(s.startswith("Seen before:") for s in d2["facts"]["items"])
    assert d2["dcs"] == d["dcs"]  # recurrence is a fact, not a reproduction: DCS unchanged
    hist = client.get(f"/api/v1/findings/{d2['id']}/history", headers=auth_headers).json()
    assert [h["id"] for h in hist["items"]] == [d2["id"], d["id"]]
    report = client.get(f"/api/v1/jobs/{job2['id']}/report", headers=auth_headers).json()
    assert report["content"]["findings_by_priority"][0]["id"] == d2["id"]
    assert any("recur from earlier jobs" in r for r in report["content"]["residual_risk"])

    # A different repository never sees this history.
    other = _repo(client, auth_headers)
    job3 = _run(client, auth_headers, other, test_settings, "run-1")
    assert _findings(client, auth_headers, job3["id"])[0]["history"]["recurring"] is False


def test_triage_is_role_checked_audited_and_etag_protected(
    client: TestClient,
    auth_headers: dict,
    engineer_headers: dict,
    viewer_headers: dict,
    test_settings: Settings,
) -> None:
    repo = _repo(client, auth_headers)
    job = _run(client, auth_headers, repo, test_settings, "t-1")
    d = _findings(client, auth_headers, job["id"])[0]
    url = f"/api/v1/findings/{d['id']}/triage"

    # Engineer may not mark false positive (HA-07 needs QA Lead for functional findings).
    r = client.post(
        url, json={"action": "mark_false_positive", "reason": "x"}, headers=engineer_headers
    )
    assert r.status_code == 403 and r.json()["error_code"] == "insufficient_role"
    # Reason is mandatory.
    r = client.post(url, json={"action": "mark_false_positive"}, headers=auth_headers)
    assert r.status_code == 422
    # Reproduction is honestly unavailable.
    r = client.post(url, json={"action": "request_reproduction"}, headers=auth_headers)
    assert r.status_code == 501 and r.json()["planned_slice"] == "2b"
    # Stale ETag.
    r = client.post(
        url,
        json={"action": "mark_false_positive", "reason": "fixture route"},
        headers={**auth_headers, "If-Match": f'"{d["id"]}:v7"'},
    )
    assert r.status_code == 412 and r.json()["error_code"] == "etag_mismatch"
    # Success with matching ETag.
    r = client.post(
        url,
        json={"action": "mark_false_positive", "reason": "fixture route"},
        headers={**auth_headers, "If-Match": f'"{d["id"]}:v1"'},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "false_positive" and body["confidence"] == "rejected"
    assert body["version"] == 2 and r.headers["ETag"] == f'"{d["id"]}:v2"'
    assert body["triage"]["reason"] == "fixture route" and body["triage"]["role"] == "QA Lead"
    assert [h["to"] for h in body["status_history"]["items"]] == ["candidate", "false_positive"]
    # Illegal transition from false_positive.
    r = client.post(
        url, json={"action": "mark_false_positive", "reason": "again"}, headers=auth_headers
    )
    assert r.status_code == 409 and r.json()["error_code"] == "invalid_state_transition"
    # Reopen (engineer allowed), then accept risk with expiry (QA Lead, HA-08 approval row).
    r = client.post(
        url, json={"action": "reopen", "reason": "it is real"}, headers=engineer_headers
    )
    assert r.status_code == 200 and r.json()["status"] == "reopened"
    assert r.json()["confidence"] == "probable"
    r = client.post(
        url, json={"action": "accept_risk", "reason": "low impact"}, headers=auth_headers
    )
    assert r.status_code == 422  # expires_at required
    exp = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    r = client.post(
        url,
        json={"action": "accept_risk", "reason": "low impact", "expires_at": exp},
        headers=auth_headers,
    )
    assert r.status_code == 200 and r.json()["status"] == "accepted_risk"
    assert r.json()["triage"]["expires_at"] is not None
    r = client.post(url, json={"action": "reopen"}, headers=viewer_headers)
    assert r.status_code == 403
    # Filters.
    assert _findings(client, auth_headers, job["id"], status="accepted_risk")[0]["id"] == d["id"]
    assert _findings(client, auth_headers, job["id"], status="candidate") == []

    with session_factory()() as s:
        events = (
            s.execute(
                select(AuditEvent)
                .where(AuditEvent.subject_id == d["id"])
                .order_by(AuditEvent.occurred_at)
            )
            .scalars()
            .all()
        )
        assert [e.action for e in events] == [
            "finding.mark_false_positive",
            "finding.reopen",
            "finding.accept_risk",
        ]
        assert verify_chain(s, events[0].org_id) is None
        assert s.get(Finding, d["id"]).version == 4


def test_false_positive_suppression_carries_over_and_duplicates_need_a_target(
    client: TestClient, auth_headers: dict, test_settings: Settings
) -> None:
    repo = _repo(client, auth_headers)
    job1 = _run(client, auth_headers, repo, test_settings, "s-1")
    d1 = _findings(client, auth_headers, job1["id"])[0]
    r = client.post(
        f"/api/v1/findings/{d1['id']}/triage",
        json={"action": "mark_false_positive", "reason": "endpoint intentionally absent"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    job2 = _run(client, auth_headers, repo, test_settings, "s-2")
    d2 = _findings(client, auth_headers, job2["id"])[0]
    assert d2["status"] == "false_positive" and d2["confidence"] == "rejected"
    assert any("Suppressed" in s for s in d2["inferred"]["items"])
    assert d2["risk_priority"] == 0.0
    report = client.get(f"/api/v1/jobs/{job2['id']}/report", headers=auth_headers).json()
    assert report["content"]["finding_summary"]["excluded"] == 1
    assert any("excluded from gates" in r for r in report["content"]["residual_risk"])
    # Duplicate marking needs a valid target and keeps evidence of both.
    r = client.post(
        f"/api/v1/findings/{d2['id']}/triage",
        json={"action": "reopen"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    r = client.post(
        f"/api/v1/findings/{d2['id']}/triage",
        json={"action": "mark_duplicate"},
        headers=auth_headers,
    )
    assert r.status_code == 422
    r = client.post(
        f"/api/v1/findings/{d2['id']}/triage",
        json={"action": "mark_duplicate", "duplicate_of": d1["id"]},
        headers=auth_headers,
    )
    assert r.status_code == 200 and r.json()["duplicate_of"] == d1["id"]
    assert client.get(f"/api/v1/findings/{d2['id']}/evidence", headers=auth_headers).json()["items"]


def test_patches_and_verification_remain_honestly_unimplemented(
    client: TestClient, auth_headers: dict
) -> None:
    r = client.get("/api/v1/jobs/job_x/patches", headers=auth_headers)
    assert r.status_code == 501 and r.json()["planned_slice"] == "3d"
    r = client.post("/api/v1/patches/pch_x/verifications", headers=auth_headers)
    assert r.status_code == 501
