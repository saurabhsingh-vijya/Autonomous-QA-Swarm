"""Phase 4 unit tests: target policy, redaction, config model, and the four target-facing engines.

The engine tests run for real against the worker-started sample target app
(``exec/fixtures/sample-target-app``) on an ephemeral loopback port. The browser tests use the
installed Playwright + Chromium; when they are missing the engine must end ``skipped`` honestly.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

import pytest
from qaswarm_exec.host.source import FixtureSourceFetcher
from qaswarm_exec.runtime.base import RunLimits
from qaswarm_exec.runtime.subprocess_runtime import SubprocessRuntime
from qaswarm_exec.targets import TargetBlocked, TargetPolicy, TargetSession, hosts_for
from qaswarm_exec.targets.policy import classify_address
from qaswarm_exec.testing import ConfigError, discover_suites, load_suite, substitute
from qaswarm_exec.testing.jsonpath import MISSING, JsonPathError, resolve
from qaswarm_exec.testing.redact import redact_headers, redact_text, redact_value
from qaswarm_exec.tools.api_tests import ApiTestsEngine
from qaswarm_exec.tools.base import CheckContext
from qaswarm_exec.tools.browser_tests import BrowserTestsEngine, playwright_status
from qaswarm_exec.tools.performance_probe import PerformanceProbeEngine, effective_limits
from qaswarm_exec.tools.registry import ENGINES, TARGET_ENGINES, get_engine
from qaswarm_exec.tools.security_checks import SecurityChecksEngine

FIXTURES = Path(__file__).resolve().parents[3] / "exec" / "fixtures"
LOCAL = {"kind": "local_fixture", "name": "sample-target-app"}


class MemorySink:
    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []

    def put(
        self, *, kind: str, label: str, media_type: str, content: bytes, deterministic: bool = True
    ) -> str:
        self.items.append(
            {"kind": kind, "label": label, "media_type": media_type, "content": content}
        )
        return f"evd_{len(self.items)}"

    def of_kind(self, kind: str) -> list[dict[str, Any]]:
        return [i for i in self.items if i["kind"] == kind]


def _ctx(
    tmp_path: Path,
    *,
    target: dict[str, Any] | None = LOCAL,
    config: dict[str, Any] | None = None,
    workspace: Path | None = None,
    settings: dict[str, Any] | None = None,
) -> CheckContext:
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    ws = workspace or tmp_path / "src"
    ws.mkdir(exist_ok=True)
    inputs: dict[str, Any] = {"config": config or {}}
    if target is not None:
        inputs["target"] = target
    return CheckContext(
        task={"task_id": "tsk_x", "inputs": inputs},
        workspace=ws,
        out_dir=out,
        runtime=SubprocessRuntime(),
        limits=RunLimits(timeout_seconds=120, output_cap_bytes=1_000_000),
        evidence=MemorySink(),
        allow_code_execution=False,
        cancel=threading.Event(),
        settings={"fixtures_dir": str(FIXTURES), **(settings or {})},
    )


def _web_app(tmp_path: Path) -> Path:
    dest = tmp_path / "web"
    FixtureSourceFetcher(FIXTURES).fetch(
        {"repository_url": "https://fixtures.local/local/sample-web-app", "ref": "main"}, dest
    )
    return dest


def _api_suite(*steps: dict[str, Any], name: str = "inline") -> dict[str, Any]:
    return {"kind": "api", "name": name, "scenarios": [{"name": "s", "steps": list(steps)}]}


# ------------------------------------------------------------------------ policy
def test_address_classification_blocks_every_internal_range() -> None:
    blocked = {
        "127.0.0.1": "loopback",
        "10.1.2.3": "private",
        "172.16.0.9": "private",
        "192.168.1.1": "private",
        "169.254.169.254": "cloud_metadata",
        "169.254.10.10": "link_local",
        "100.64.0.1": "cgnat",
        "0.0.0.0": "unspecified",  # noqa: S104 - classification input, not a bind address
        "::1": "loopback",
        "fd12::1": "private",
        "fe80::1": "link_local",
        "::ffff:10.0.0.1": "private",
    }
    for ip, why in blocked.items():
        assert classify_address(ip) == why, ip
    assert classify_address("93.184.216.34") is None
    assert classify_address("2606:2800:220:1:248:1893:25c8:1946") is None


def test_policy_refuses_unauthorised_and_private_hosts_unless_local_mode() -> None:
    policy = TargetPolicy(allowed_hosts=hosts_for("http://127.0.0.1:8080"))
    with pytest.raises(TargetBlocked) as exc:
        policy.check_url("http://127.0.0.1:8080/")
    assert exc.value.reason == "private_address" and "AQS_EXEC_ALLOW_LOCAL_TARGETS" in str(
        exc.value
    )
    with pytest.raises(TargetBlocked, match="host_not_authorized"):
        policy.check_url("http://example.com/")
    with pytest.raises(TargetBlocked, match="scheme_not_allowed"):
        policy.check_url("ftp://127.0.0.1:8080/")
    with pytest.raises(TargetBlocked, match="userinfo_not_allowed"):
        policy.check_url("http://user:pw@127.0.0.1:8080/")
    local = TargetPolicy(allowed_hosts=hosts_for("http://127.0.0.1:8080"), allow_local=True)
    assert local.check_url("http://127.0.0.1:8080/x") == ("127.0.0.1", 8080)
    with pytest.raises(TargetBlocked, match="host_not_authorized"):
        local.check_url("http://169.254.169.254/latest/")  # still outside the authorised set
    assert hosts_for("https://app.example.test") == {"app.example.test", "app.example.test:443"}


def test_target_session_rejects_registered_private_target_and_missing_descriptor(
    tmp_path: Path,
) -> None:
    desc = {"kind": "registered", "target_id": "tgt_1", "base_url": "http://127.0.0.1:9"}
    with pytest.raises(TargetBlocked, match="private_address"):
        TargetSession(desc, fixtures_dir=None, allow_local=False, out_dir=tmp_path).__enter__()
    with pytest.raises(TargetBlocked, match="no_target"):
        TargetSession(None, fixtures_dir=None, allow_local=False, out_dir=tmp_path).__enter__()
    with pytest.raises(TargetBlocked, match="fixtures_disabled"):
        TargetSession(LOCAL, fixtures_dir=None, allow_local=False, out_dir=tmp_path).__enter__()


# ---------------------------------------------------------------------- redaction
def test_redaction_masks_credentials_in_headers_text_and_values() -> None:
    headers = redact_headers(
        {"Authorization": "Bearer abc.def.ghi", "Cookie": "session=1", "Accept": "text/html"}
    )
    assert headers == {"Authorization": "[REDACTED]", "Cookie": "[REDACTED]", "Accept": "text/html"}
    text = redact_text(
        "authorization: Bearer xyz123 token=abcdef https://u:p@h.test/ AKIAIOSFODNN7EXAMPLE"
    )
    assert "xyz123" not in text and "abcdef" not in text and ":p@" not in text
    assert "AKIAIOSFODNN7EXAMPLE" not in text
    value = redact_value({"password": "hunter2", "nested": {"api_key": "k", "ok": "v"}})
    assert value == {"password": "[REDACTED]", "nested": {"api_key": "[REDACTED]", "ok": "v"}}


# ------------------------------------------------------------------------ jsonpath
def test_jsonpath_subset() -> None:
    doc = {"items": [{"id": 1, "name": "a b"}, {"id": 2}], "status": "ok", "n": None}
    assert resolve(doc, "$.status") == "ok"
    assert resolve(doc, "$.items[0].id") == 1
    assert resolve(doc, "$.items[-1].id") == 2
    assert resolve(doc, "$.items.length()") == 2
    assert resolve(doc, "$.items[*].id") == [1, 2]
    assert resolve(doc, "$.items[0]['name']") == "a b"
    assert resolve(doc, "$.n") is None
    assert resolve(doc, "$.missing.deeper") is MISSING
    with pytest.raises(JsonPathError):
        resolve(doc, "items")
    with pytest.raises(JsonPathError):
        resolve(doc, "$.items[?(@.id==1)]")


# -------------------------------------------------------------------- config model
def test_suite_loader_validates_and_substitutes(tmp_path: Path) -> None:
    suites = discover_suites(_web_app(tmp_path), kind="api")
    assert [s.name for s in suites] == ["items-api"] and suites[0].step_count == 5
    browser = discover_suites(_web_app(tmp_path), kind="browser")
    assert [s.name for s in browser] == ["home-page"] and browser[0].scenarios[0].steps[
        3
    ].action == "click"
    assert substitute({"a": "${x}", "b": "v=${x}", "c": "${obj}"}, {"x": 1, "obj": {"k": 2}}) == {
        "a": 1,
        "b": "v=1",
        "c": {"k": 2},
    }
    with pytest.raises(ConfigError, match="undefined variable"):
        substitute("${nope}", {})
    with pytest.raises(ConfigError, match="unknown assertion"):
        load_suite(_api_suite({"request": {"path": "/"}, "expect": [{"sql": 1}]}), "x")
    with pytest.raises(ConfigError, match="unsupported method"):
        load_suite(_api_suite({"request": {"method": "BREW", "path": "/"}}), "x")
    with pytest.raises(ConfigError, match="exactly one action"):
        load_suite({"kind": "browser", "scenarios": [{"steps": [{"click": "a", "fill": {}}]}]}, "x")
    with pytest.raises(ConfigError, match="escapes"):
        discover_suites(tmp_path, kind="api", paths=["../etc"])


# ------------------------------------------------------------------- api engine
def test_api_engine_runs_the_fixture_suite_against_the_local_target(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, workspace=_web_app(tmp_path))
    r = ApiTestsEngine().run(ctx)
    assert r.outcome == "passed", r.message
    assert (
        r.summary["steps"] == 5
        and r.summary["passed"] == 5
        and r.summary["target_kind"] == "local_fixture"
    )
    assert r.summary["timings"]["count"] == 5 and r.summary["timings"]["p95_ms"] >= 0
    statuses = {t.node_id: t.status for t in r.tests}
    assert statuses["items-api::create and fetch an item::fetch created item"] == "passed"
    report = json.loads(ctx.evidence.of_kind("api_test_report")[0]["content"])  # type: ignore[attr-defined]
    created = next(s for s in report["steps"] if s["step"] == "create item")
    assert created["response"]["status"] == 201 and created["captured"] == ["item_id"]
    assert all(a["passed"] for a in created["assertions"])


def test_api_engine_negative_scenarios(tmp_path: Path) -> None:
    engine = ApiTestsEngine()
    # assertion failure stops the scenario; later steps are skipped, evidence redacts the header
    cfg = {
        "inline": [
            _api_suite(
                {
                    "name": "protected",
                    "request": {
                        "path": "/api/protected",
                        "headers": {"Authorization": "Bearer fixture-token-not-a-secret"},
                    },
                    "expect": [{"status": 200}, {"json_path": {"path": "$.ok", "equals": False}}],
                },
                {"name": "after", "request": {"path": "/health"}, "expect": [{"status": 200}]},
            )
        ]
    }
    ctx = _ctx(tmp_path, config=cfg)
    r = engine.run(ctx)
    assert r.outcome == "failed" and r.summary == {**r.summary, "failed": 1, "skipped": 1}
    assert "$.ok == true, expected false" in (r.message or "")
    evidence = ctx.evidence.of_kind("api_test_report")[0]["content"].decode()  # type: ignore[attr-defined]
    assert "fixture-token-not-a-secret" not in evidence and "[REDACTED]" in evidence

    # redirect to a private host is refused at the hop, even from an allowed local target
    r = engine.run(
        _ctx(tmp_path, config={"inline": [_api_suite({"request": {"path": "/redirect-private"}})]})
    )
    assert r.outcome == "failed" and "host_not_authorized" in (r.message or "")

    # timeout → timed_out status
    r = engine.run(
        _ctx(
            tmp_path,
            config={
                "inline": [
                    _api_suite({"request": {"path": "/api/slow?ms=3000"}, "timeout_ms": 300})
                ]
            },
        )
    )
    assert (
        r.outcome == "failed" and r.tests[0].status == "timed_out" and r.summary["timed_out"] == 1
    )

    # blocked external target → skipped with blocked tests, nothing executed
    blocked = {"kind": "registered", "target_id": "tgt_1", "base_url": "http://127.0.0.1:9"}
    r = engine.run(
        _ctx(tmp_path, target=blocked, config={"inline": [_api_suite({"request": {"path": "/"}})]})
    )
    assert r.outcome == "skipped" and r.summary["blocked"] and r.tests[0].status == "blocked"

    # no suites → skipped; malformed suite → error
    assert engine.run(_ctx(tmp_path)).outcome == "skipped"
    assert engine.run(_ctx(tmp_path, config={"inline": [{"kind": "api"}]})).outcome == "error"


def test_api_engine_accepts_registered_loopback_target_in_local_mode(tmp_path: Path) -> None:
    """Controlled local testing: a registered target on loopback with AQS_EXEC_ALLOW_LOCAL_TARGETS."""
    with TargetSession(
        LOCAL, fixtures_dir=str(FIXTURES), allow_local=False, out_dir=tmp_path
    ) as app:
        registered = {"kind": "registered", "target_id": "tgt_1", "base_url": app.base_url}
        cfg = {
            "inline": [_api_suite({"request": {"path": "/health"}, "expect": [{"status": 200}]})]
        }
        assert (
            ApiTestsEngine().run(_ctx(tmp_path, target=registered, config=cfg)).outcome == "skipped"
        )
        ok = ApiTestsEngine().run(
            _ctx(tmp_path, target=registered, config=cfg, settings={"allow_local_targets": True})
        )
        assert ok.outcome == "passed", ok.message


# -------------------------------------------------------------- security engine
def test_security_checks_are_read_only_and_find_the_planted_issues(tmp_path: Path) -> None:
    quick = SecurityChecksEngine().run(_ctx(tmp_path, config={"profile": "quick"}))
    assert quick.outcome == "failed" and quick.summary["paths"] == 1
    quick_checks = {t.node_id.split("::")[1] for t in quick.tests}
    assert "content_security_policy" in quick_checks and "not_found_probe" not in quick_checks

    ctx = _ctx(
        tmp_path,
        config={"profile": "standard", "paths": ["/", "/login", "/boom", "/redirect-private"]},
    )
    r = SecurityChecksEngine().run(ctx)
    assert r.outcome == "failed"
    failed = {t.node_id for t in r.tests if t.status == "failed"}
    assert "security::content_security_policy::/" in failed
    assert "security::version_disclosure::/" in failed
    assert "security::verbose_error_body::/boom" in failed
    assert "security::redirect_sanity::/redirect-private" in failed
    assert "security::x_content_type_options::/" not in failed  # nosniff is set by the app
    assert any(
        t.node_id.startswith("security::not_found_probe::") and t.status == "passed"
        for t in r.tests
    )
    report = json.loads(ctx.evidence.of_kind("security_report")[0]["content"])  # type: ignore[attr-defined]
    assert "certification" in report["disclaimer"]
    login = next(o for o in report["observations"] if o["path"] == "/login")
    assert login["headers"]["set-cookie"] == "[REDACTED]"
    assert r.summary["high"] == 1 and r.summary["medium"] >= 3
    # Only GET requests were issued: the item store is untouched.
    with TargetSession(LOCAL, fixtures_dir=str(FIXTURES), allow_local=False, out_dir=tmp_path):
        pass


# ----------------------------------------------------------- performance engine
def test_performance_probe_is_bounded_and_reports_percentiles(tmp_path: Path) -> None:
    limits = effective_limits(
        {"profile": "baseline", "max_requests": 10_000, "concurrency": 99}, {}
    )
    assert limits["max_requests"] == 500 and limits["concurrency"] == 10
    limits = effective_limits({"profile": "smoke"}, {"perf_max_requests": 20})
    assert (
        limits["max_requests"] == 20
        and limits["concurrency"] == 2
        and limits["duration_seconds"] == 10
    )

    ctx = _ctx(
        tmp_path,
        config={
            "profile": "smoke",
            "max_requests": 24,
            "concurrency": 3,
            "paths": ["/health", "/api/items"],
        },
    )
    r = PerformanceProbeEngine().run(ctx)
    assert r.outcome == "passed", r.message
    assert r.summary["requests"] == 24 and r.summary["error_rate"] == 0 and r.summary["p95_ms"] >= 0
    report = json.loads(ctx.evidence.of_kind("performance_report")[0]["content"])  # type: ignore[attr-defined]
    assert report["metrics"]["status_codes"] == {"200": 24} and set(report["per_path"]) == {
        "/health",
        "/api/items",
    }
    assert {t.node_id for t in r.tests} == {"perf::/health", "perf::/api/items"}

    strict = PerformanceProbeEngine().run(
        _ctx(tmp_path, config={"profile": "smoke", "max_requests": 6, "thresholds": {"p95_ms": 0}})
    )
    assert strict.outcome == "failed" and "p95" in (strict.message or "")
    assert (
        PerformanceProbeEngine().run(_ctx(tmp_path, config={"profile": "load"})).outcome == "error"
    )
    assert (
        PerformanceProbeEngine().run(_ctx(tmp_path, config={"method": "POST"})).outcome == "error"
    )


# --------------------------------------------------------------- browser engine
def test_browser_engine_skips_honestly_when_playwright_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "qaswarm_exec.tools.browser_tests.playwright_status",
        lambda: (False, "Playwright is not installed"),
    )
    r = BrowserTestsEngine().run(_ctx(tmp_path, workspace=_web_app(tmp_path)))
    assert r.outcome == "skipped" and "not installed" in (r.message or "")
    assert BrowserTestsEngine().run(_ctx(tmp_path)).outcome == "skipped"  # no suites


@pytest.mark.skipif(not playwright_status()[0], reason=playwright_status()[1])
def test_browser_engine_runs_the_fixture_suite_with_evidence(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, workspace=_web_app(tmp_path))
    r = BrowserTestsEngine().run(ctx)
    assert r.outcome == "passed", r.message
    assert (
        r.summary["steps"] == 9
        and r.summary["passed"] == 9
        and r.summary["browser"].startswith("chromium")
    )
    shots = ctx.evidence.of_kind("screenshot")  # type: ignore[attr-defined]
    assert (
        len(shots) == 1
        and shots[0]["media_type"] == "image/png"
        and shots[0]["content"][:4] == b"\x89PNG"
    )
    console = json.loads(ctx.evidence.of_kind("browser_console")[0]["content"])  # type: ignore[attr-defined]
    assert any("counter is now 1" in c["text"] for c in console)
    assert any(c["type"] == "warning" for c in console)


@pytest.mark.skipif(not playwright_status()[0], reason=playwright_status()[1])
def test_browser_engine_negative_scenarios(tmp_path: Path) -> None:
    def suite(*steps: dict[str, Any]) -> dict[str, Any]:
        return {
            "kind": "browser",
            "name": "neg",
            "scenarios": [{"name": "s", "steps": list(steps)}],
        }

    # failing assertion → failed step, failure screenshot, following steps skipped
    ctx = _ctx(
        tmp_path,
        config={
            "inline": [
                suite(
                    {"goto": "/"},
                    {"name": "wrong", "expect": {"text": {"selector": "#count", "equals": "7"}}},
                    {"name": "after", "click": "#inc"},
                )
            ]
        },
    )
    r = BrowserTestsEngine().run(ctx)
    assert r.outcome == "failed" and [t.status for t in r.tests] == ["passed", "failed", "skipped"]
    assert (
        "expected '7'" in (r.tests[1].message or "")
        and len(ctx.evidence.of_kind("screenshot")) == 1
    )  # type: ignore[attr-defined]

    # navigation that redirects to the cloud metadata address is refused
    ctx = _ctx(tmp_path, config={"inline": [suite({"name": "meta", "goto": "/redirect-private"})]})
    r = BrowserTestsEngine().run(ctx)
    assert r.outcome == "failed" and r.summary["policy_violations"] >= 1
    report = json.loads(ctx.evidence.of_kind("browser_test_report")[0]["content"])  # type: ignore[attr-defined]
    assert report["policy_violations"][0]["url"].startswith("http://169.254.169.254")

    # selector that never appears → timed_out within the step timeout
    r = BrowserTestsEngine().run(
        _ctx(
            tmp_path,
            config={
                "inline": [
                    suite({"goto": "/"}, {"name": "never", "click": "#nope", "timeout_ms": 500})
                ]
            },
        )
    )
    assert r.outcome == "failed" and r.tests[1].status == "timed_out"

    # blocked external target → skipped, nothing launched
    blocked = {"kind": "registered", "target_id": "tgt_1", "base_url": "http://10.0.0.1"}
    r = BrowserTestsEngine().run(
        _ctx(tmp_path, target=blocked, config={"inline": [suite({"goto": "/"})]})
    )
    assert r.outcome == "skipped" and r.summary["blocked"]


# -------------------------------------------------------------------- registry
def test_registry_exposes_phase4_engines() -> None:
    assert set(ENGINES) >= TARGET_ENGINES and len(ENGINES) == 8
    for engine_id in TARGET_ENGINES:
        engine = get_engine(engine_id)
        assert engine.executes_repository_code is False and engine.tool_version()
