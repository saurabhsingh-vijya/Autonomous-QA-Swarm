"""Auth modes without a database: 401 when dev auth is off, header handling when it is on."""

from __future__ import annotations

from fastapi.testclient import TestClient

from qaswarm.api.app import create_app
from qaswarm.api.auth import Principal, get_principal
from qaswarm.api.deps import get_db
from qaswarm.config import Settings, get_settings
from qaswarm.domain.enums import Role


def _client(settings: Settings) -> TestClient:
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_db] = lambda: iter([None])
    return TestClient(app, raise_server_exceptions=False)


def test_without_dev_auth_every_api_call_is_401_problem() -> None:
    client = _client(Settings(dev_auth=False))
    r = client.get("/api/v1/projects", headers={"X-Dev-User": "x", "X-Dev-Role": "QA Lead"})
    assert r.status_code == 401
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["error_code"] == "unauthenticated" and "slice 3e" in body["detail"]
    assert body["instance"] == "/api/v1/projects" and body["trace_id"]
    assert client.get("/healthz").status_code == 200  # health is outside /api/v1


def test_dev_auth_requires_user_header_and_rejects_unknown_role() -> None:
    client = _client(Settings(dev_auth=True))
    assert client.get("/api/v1/projects").json()["error_code"] == "unauthenticated"
    r = client.get("/api/v1/projects", headers={"X-Dev-User": "u", "X-Dev-Role": "Root"})
    assert r.status_code == 400 and "Allowed roles" in r.json()["detail"]


def test_dev_auth_attaches_principal_and_501_stubs_name_their_slice() -> None:
    settings = Settings(dev_auth=True)
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_principal] = lambda: Principal("u", Role.QA_LEAD, "org_x", "dev")
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/api/v1/jobs/job_x/quality-gates")
    assert r.status_code == 501
    assert r.json()["error_code"] == "not_implemented" and r.json()["planned_slice"] == "2d"
    r = client.get("/api/v1/openapi.json")
    paths = r.json()["paths"]
    assert "/api/v1/jobs/{job_id}/release-decision" in paths and "/api/v1/jobs" in paths


def test_correlation_id_is_echoed_or_generated() -> None:
    client = _client(Settings(dev_auth=False))
    r = client.get("/healthz", headers={"X-Correlation-ID": "abc-123"})
    assert r.headers["X-Correlation-ID"] == "abc-123"
    assert len(client.get("/healthz").headers["X-Correlation-ID"]) == 32


def test_unknown_route_is_problem_json() -> None:
    client = _client(Settings(dev_auth=False))
    r = client.get("/nope")
    assert r.status_code == 404 and r.json()["error_code"] == "not_found"
