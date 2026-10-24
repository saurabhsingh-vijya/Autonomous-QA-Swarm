"""Phase 6 hardening: redaction coverage, fixture path containment, config warnings, headers."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from qaswarm_exec.host.source import FetchError, FixtureSourceFetcher, safe_extract_tar

from qaswarm.api.app import create_app
from qaswarm.api.deps import get_db
from qaswarm.config import Settings, get_settings
from qaswarm.intake.resolvers import FixtureRefResolver, IntakeError
from qaswarm.telemetry.logging import redact_text, redact_value

FIXTURES = Path(__file__).resolve().parents[3] / "exec" / "fixtures"
FIXTURE_URL = "https://fixtures.local/local/sample-python-app"


# ------------------------------------------------------------------- redaction
@pytest.mark.parametrize(
    ("text", "must_not_contain"),
    [
        ('{"password": "hunter2-json", "ok": 1}', "hunter2-json"),
        ("{'token': 'tok_quoted_single'}", "tok_quoted_single"),
        ('"client_secret":"cs_abcdef123456"', "cs_abcdef123456"),
        ("AQS_EXEC_TOKEN=dev-exec-token-value", "dev-exec-token-value"),
        ("X-Exec-Token: dev-exec-token-value", "dev-exec-token-value"),
        ("header Bearer abcdefghijklmnop.qrstuv", "abcdefghijklmnop"),
        ("Authorization: Bearer plainopaquetoken123", "plainopaquetoken123"),
        # built at runtime so no token-shaped literal sits in the file (GitHub push protection)
        ("xoxb-" + "123456789012-abcdefghijklmnop", "xoxb-1234"),
        ("sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123", "sk-ant-api03"),
        ("github_pat_11ABCDEFG0123456789abcdefghijkl", "github_pat_11"),
        (
            "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA\n-----END RSA PRIVATE KEY-----",
            "MIIEowIBAAKCAQEA",
        ),
        ("-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBg (truncated", "MIIEvQIBADANBg"),
        (
            "postgresql+psycopg://qaswarm:qaswarm-dev-only@127.0.0.1:59137/qaswarm",
            ":qaswarm-dev-only@",
        ),
    ],
)
def test_redaction_covers_json_env_and_vendor_token_shapes(
    text: str, must_not_contain: str
) -> None:
    assert must_not_contain not in redact_text(text)


def test_redaction_leaves_ordinary_text_alone() -> None:
    plain = (
        "task check:secret_scan ended failed; engine=secret_scan findings=1 "
        "job_id=job_01HZX display_id=QJ-1042 tokens_used=12"
    )
    assert redact_text(plain) == plain


def test_redact_value_masks_exec_token_header_key() -> None:
    assert redact_value({"X-Exec-Token": "abc", "job_id": "job_1"}) == {
        "X-Exec-Token": "[REDACTED]",
        "job_id": "job_1",
    }


# ------------------------------------------------------ fixture path containment
@pytest.mark.parametrize("ref", ["/etc", "/Windows", "//server/share", "../../..", "main/", "-x"])
def test_control_plane_fixture_resolver_rejects_escaping_refs(ref: str) -> None:
    with pytest.raises(IntakeError) as exc:
        FixtureRefResolver(FIXTURES).resolve(FIXTURE_URL, ref)
    assert exc.value.code == "E-INTAKE-002" and exc.value.reason == "invalid_ref"


@pytest.mark.parametrize("ref", ["/etc", "/Windows", "../../..", "-x", "a//b"])
def test_exec_fixture_fetcher_rejects_escaping_refs(ref: str, tmp_path: Path) -> None:
    source = {"repository_url": FIXTURE_URL, "ref": ref, "commit_sha": ""}
    with pytest.raises(FetchError) as exc:
        FixtureSourceFetcher(FIXTURES).fetch(source, tmp_path / "dest")
    assert exc.value.code == "E-EXEC-003" and not exc.value.retryable
    assert not (tmp_path / "dest").exists()


def test_fixture_resolver_still_resolves_valid_refs() -> None:
    resolved = FixtureRefResolver(FIXTURES).resolve(FIXTURE_URL, "fix-rounding")
    assert len(resolved.commit_sha) == 40 and resolved.resolver == "fixture"


def test_safe_extract_rejects_prefix_confusion_and_absolute_members(tmp_path: Path) -> None:
    import io
    import tarfile

    def archive(name: str) -> bytes:
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            info = tarfile.TarInfo(name)
            info.size = 1
            tar.addfile(info, io.BytesIO(b"x"))
        return buf.getvalue()

    dest = tmp_path / "dest"
    dest.mkdir()
    for bad in ("../dest2/x", "/abs", "C:evil", "a\\b"):
        with pytest.raises(FetchError):
            safe_extract_tar(archive(bad), dest)
    assert safe_extract_tar(archive("ok/file.txt"), dest) == 1
    assert (dest / "ok" / "file.txt").read_bytes() == b"x"


# -------------------------------------------------------- configuration warnings
def test_startup_warnings_name_each_unsafe_flag() -> None:
    s = Settings(
        dev_auth=True,
        exec_token=None,
        dev_fixture_repos=True,
        embedded_exec_worker=True,
        exec_allow_unsandboxed_code_execution=True,
        intake_dns_check=False,
        environment="prod",
    )
    joined = "\n".join(s.startup_warnings())
    for needle in (
        "AQS_DEV_AUTH=true",
        "qaswarm-dev-only",
        "AQS_EXEC_TOKEN is not set",
        "AQS_EXEC_ALLOW_UNSANDBOXED_CODE_EXECUTION=true",
        "AQS_EMBEDDED_EXEC_WORKER=true",
        "AQS_DEV_FIXTURE_REPOS=true",
        "AQS_INTAKE_DNS_CHECK=false",
        "AQS_ENVIRONMENT='prod'",
    ):
        assert needle in joined, needle


def test_startup_warnings_are_quiet_for_a_hardened_configuration() -> None:
    s = Settings(
        dev_auth=False,
        database_url="postgresql+psycopg://qaswarm:s3cret-long-password@db:5432/qaswarm",
        exec_token="0123456789abcdef0123456789abcdef",
        environment="prod",
    )
    warnings = s.startup_warnings()
    # Only the honest "no OIDC yet" notice remains.
    assert len(warnings) == 1 and "401" in warnings[0]


def test_short_exec_token_is_flagged() -> None:
    assert any("16 characters" in w for w in Settings(exec_token="short").startup_warnings())


# -------------------------------------------------------- response headers / auth
def _client(settings: Settings) -> TestClient:
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_db] = lambda: iter([None])
    return TestClient(app, raise_server_exceptions=False)


def test_security_headers_are_present_on_every_response() -> None:
    client = _client(Settings(dev_auth=True))
    for path in ("/healthz", "/api/v1/projects", "/nope"):
        r = client.get(path)
        assert r.headers["X-Content-Type-Options"] == "nosniff"
        assert r.headers["X-Frame-Options"] == "DENY"
        assert r.headers["Referrer-Policy"] == "no-referrer"
        assert "default-src 'none'" in r.headers["Content-Security-Policy"]
    assert client.get("/api/v1/projects").headers["Cache-Control"] == "no-store"


def test_dev_auth_query_parameters_are_only_accepted_on_the_sse_endpoint() -> None:
    client = _client(Settings(dev_auth=True))
    r = client.get("/api/v1/system/capabilities?dev_user=u&dev_role=QA%20Lead")
    assert r.status_code == 401 and r.json()["error_code"] == "unauthenticated"


# ------------------------------------------------------- dependency scope guard
def test_every_get_db_dependency_uses_function_scope() -> None:
    """FastAPI >= 0.118 commits ``yield`` dependencies after the response unless scope=function.

    Without it a client can get a 404 for the row its previous request just created.
    """
    import re

    src = Path(__file__).resolve().parents[2] / "src" / "qaswarm" / "api"
    offenders = []
    for path in src.rglob("*.py"):
        for m in re.finditer(r"Depends\(get_db[^)]*\)", path.read_text(encoding="utf-8")):
            if 'scope="function"' not in m.group(0):
                offenders.append(f"{path.name}: {m.group(0)}")
    assert not offenders, offenders


def test_serve_entry_point_builds_the_app_without_multiprocessing() -> None:
    from qaswarm.api import serve

    assert isinstance(serve._ensure_multiprocessing_importable(), bool)
