"""API testing engine: declarative HTTP suites with assertions and response-time recording.

Every request goes through :class:`CheckedClient` (policy at connect time, manual redirect walk).
One :class:`TestResult` per step (``suite::scenario::step``). A failing step ends its scenario;
the remaining steps are ``skipped`` with the reason. Evidence: ``api_test_report`` with redacted
request/response summaries and timings. This engine never executes repository code.
"""

from __future__ import annotations

import json
import operator
import re
from collections.abc import Callable
from typing import Any

import httpx

from qaswarm_exec import __version__
from qaswarm_exec.targets import ResolvedTarget, TargetBlocked
from qaswarm_exec.targets.http import CheckedClient, Exchange
from qaswarm_exec.targets.local_app import LocalTargetError
from qaswarm_exec.testing.config import (
    ConfigError,
    Environment,
    Step,
    TestSuite,
    discover_suites,
    load_environments,
    load_inline,
    substitute,
)
from qaswarm_exec.testing.jsonpath import MISSING, JsonPathError, resolve
from qaswarm_exec.testing.redact import redact_headers, redact_url, redact_value, summarize_body
from qaswarm_exec.tools.base import (
    ERROR,
    FAILED,
    PASSED,
    SKIPPED,
    CheckContext,
    CheckResult,
    TestResult,
)
from qaswarm_exec.tools.targeted import (
    blocked_result,
    engine_config,
    local_target_error,
    open_target,
    timing_summary,
)

MAX_REGEX = 500


class AssertionFailed(Exception):
    pass


def _cmp(actual: Any, params: dict[str, Any], what: str) -> None:
    """Shared comparison operators: equals, in, contains, matches, exists, lt/lte/gt/gte, length."""
    if "exists" in params:
        present = actual is not MISSING
        if present != bool(params["exists"]):
            raise AssertionFailed(f"{what} {'exists' if present else 'is missing'}")
        if not params["exists"]:
            return
    if actual is MISSING:
        raise AssertionFailed(f"{what} is missing")
    if "length" in params:
        try:
            actual = len(actual)
        except TypeError as exc:
            raise AssertionFailed(f"{what} has no length") from exc
        params = {"equals": params["length"], **{k: v for k, v in params.items() if k != "length"}}
    if "equals" in params and actual != params["equals"]:
        raise AssertionFailed(f"{what} == {_short(actual)}, expected {_short(params['equals'])}")
    if "in" in params and actual not in params["in"]:
        raise AssertionFailed(f"{what} == {_short(actual)}, expected one of {params['in']}")
    if "contains" in params:
        needle = params["contains"]
        ok = (isinstance(actual, str) and str(needle) in actual) or (
            isinstance(actual, list | dict) and needle in actual
        )
        if not ok:
            raise AssertionFailed(f"{what} does not contain {_short(needle)}")
    if "matches" in params:
        pattern = str(params["matches"])[:MAX_REGEX]
        if not isinstance(actual, str) or not re.search(pattern, actual):
            raise AssertionFailed(f"{what} does not match /{pattern}/")
    comparators: list[tuple[str, Callable[[Any, Any], bool]]] = [
        ("lt", operator.lt),
        ("lte", operator.le),
        ("gt", operator.gt),
        ("gte", operator.ge),
    ]
    for op, fn in comparators:
        if op in params:
            try:
                if not fn(actual, params[op]):
                    raise AssertionFailed(f"{what} == {_short(actual)}, expected {op} {params[op]}")
            except TypeError as exc:
                raise AssertionFailed(f"{what} is not comparable with {params[op]!r}") from exc


def _short(value: Any) -> str:
    text = json.dumps(value, default=str) if not isinstance(value, str) else repr(value)
    return text if len(text) <= 120 else text[:117] + "..."


def evaluate(assertion_kind: str, params: dict[str, Any], ex: Exchange) -> None:
    if assertion_kind == "status":
        _cmp(ex.status, params, "status")
    elif assertion_kind == "header":
        name = str(params["name"]).lower()
        value = ex.headers.get(name, MISSING)
        _cmp(
            value,
            {k: v for k, v in params.items() if k != "name"} or {"exists": True},
            f"header {name}",
        )
    elif assertion_kind == "json_path":
        try:
            doc = ex.json()
        except ValueError as exc:
            raise AssertionFailed("response body is not JSON") from exc
        try:
            actual = resolve(doc, str(params["path"]))
        except JsonPathError as exc:
            raise AssertionFailed(str(exc)) from exc
        ops = {k: v for k, v in params.items() if k != "path"} or {"exists": True}
        _cmp(actual, ops, params["path"])
    elif assertion_kind == "body_contains":
        if str(params["value"]) not in ex.text():
            raise AssertionFailed(f"body does not contain {_short(params['value'])}")
    elif assertion_kind == "body_matches":
        if not re.search(str(params["value"])[:MAX_REGEX], ex.text()):
            raise AssertionFailed(f"body does not match /{params['value']}/")
    elif assertion_kind == "response_time_ms":
        if ex.elapsed_ms >= int(params["lt"]):
            raise AssertionFailed(f"response time {ex.elapsed_ms} ms, expected < {params['lt']} ms")
    else:  # pragma: no cover - the loader rejects unknown kinds
        raise AssertionFailed(f"unknown assertion {assertion_kind}")


def _exchange_record(
    step: Step, params: dict[str, Any], url: str, ex: Exchange | None
) -> dict[str, Any]:
    body = params.get("body")
    req_body: dict[str, Any] | None = None
    if body is not None:
        req_body = summarize_body(str(body).encode())
    elif params.get("json") is not None:
        req_body = {"json": redact_value(params["json"])}
    rec: dict[str, Any] = {
        "step": step.name,
        "request": {
            "method": params["method"],
            "url": redact_url(url),
            "headers": redact_headers(params.get("headers")),
            "body": req_body,
        },
    }
    if ex is not None:
        rec["response"] = {
            "status": ex.status,
            "final_url": redact_url(ex.final_url),
            "hops": [{"url": redact_url(h.url), "status": h.status} for h in ex.hops],
            "headers": redact_headers(ex.headers),
            "body": summarize_body(ex.body),
            "elapsed_ms": ex.elapsed_ms,
        }
    return rec


class ApiTestsEngine:
    engine_id = "api_tests"
    display_name = "API tests (declarative HTTP suites)"
    executes_repository_code = False

    def tool_version(self) -> str:
        return f"qaswarm_exec {__version__} httpx {httpx.__version__}"

    # ------------------------------------------------------------------ suites
    def _load(
        self, ctx: CheckContext, cfg: dict[str, Any]
    ) -> tuple[list[TestSuite], dict[str, Environment]]:
        suites: list[TestSuite] = []
        inline = cfg.get("inline")
        if isinstance(inline, list) and inline:
            suites += load_inline(inline, kind="api")
        paths = cfg.get("suites")
        if paths or not suites:
            suites += discover_suites(
                ctx.workspace, kind="api", paths=[str(p) for p in paths] if paths else None
            )
        return suites, load_environments(cfg.get("environments"))

    def run(self, ctx: CheckContext) -> CheckResult:
        cfg = engine_config(ctx)
        try:
            suites, job_envs = self._load(ctx, cfg)
        except ConfigError as exc:
            return CheckResult(ERROR, f"invalid test configuration: {exc}", {}, exit_code=None)
        if not suites:
            return CheckResult(
                SKIPPED,
                "No API suites found (.qaswarm/tests/*.yaml with kind: api, explicit paths or inline).",
                {"suites": 0},
            )
        planned = [
            TestResult(f"{s.name}::{sc.name}::{st.name}", st.name, "skipped", 0, s.source)
            for s in suites
            for sc in s.scenarios
            for st in sc.steps
        ]
        try:
            with open_target(ctx) as target:
                return self._run_suites(ctx, cfg, suites, job_envs, target)
        except TargetBlocked as exc:
            return blocked_result(exc, planned)
        except LocalTargetError as exc:
            return local_target_error(exc)

    def _run_suites(
        self,
        ctx: CheckContext,
        cfg: dict[str, Any],
        suites: list[TestSuite],
        job_envs: dict[str, Environment],
        target: ResolvedTarget,
    ) -> CheckResult:
        tests: list[TestResult] = []
        records: list[dict[str, Any]] = []
        timings: list[int] = []
        log_lines: list[str] = []
        with CheckedClient(target.policy) as client:
            for suite in suites:
                env = self._environment(suite, cfg, job_envs)
                for scenario in suite.scenarios:
                    variables: dict[str, Any] = {**env.variables, **suite.data, **scenario.data}
                    failed = False
                    for step in scenario.steps:
                        node = f"{suite.name}::{scenario.name}::{step.name}"
                        if failed or ctx.cancel.is_set():
                            tests.append(
                                TestResult(
                                    node,
                                    step.name,
                                    "skipped",
                                    0,
                                    suite.source,
                                    "skipped: an earlier step in the scenario failed",
                                )
                            )
                            continue
                        result, record = self._run_step(
                            client, target, env, step, variables, node, suite.source
                        )
                        tests.append(result)
                        records.append(record)
                        if "response" in record:
                            timings.append(int(record["response"]["elapsed_ms"]))
                        log_lines.append(
                            f"{result.status:>9}  {node}  {result.duration_ms} ms"
                            + (f"  {result.message}" if result.message else "")
                        )
                        if result.status != "passed":
                            failed = True
        report = {
            "engine": self.engine_id,
            "target": {
                "kind": target.kind,
                "base_url": redact_url(target.base_url),
                "target_id": target.target_id,
            },
            "suites": [
                {
                    "name": s.name,
                    "source": s.source,
                    "scenarios": len(s.scenarios),
                    "steps": s.step_count,
                }
                for s in suites
            ],
            "timings": timing_summary(timings),
            "steps": records,
        }
        report_id = ctx.evidence.put(
            kind="api_test_report",
            label="API test report (redacted)",
            media_type="application/json",
            content=json.dumps(report, indent=1, default=str).encode(),
        )
        counts = {
            s: sum(1 for t in tests if t.status == s)
            for s in ("passed", "failed", "skipped", "timed_out", "blocked")
        }
        summary = {
            "suites": len(suites),
            "steps": len(tests),
            **counts,
            "timings": report["timings"],
            "target_kind": target.kind,
        }
        log = "\n".join(log_lines) + "\n"
        bad = [t for t in tests if t.status in ("failed", "timed_out")]
        if bad:
            msg = f"{len(bad)} API step(s) failed: " + "; ".join(
                f"{t.node_id} — {t.message}" for t in bad[:3]
            )
            return CheckResult(
                FAILED, msg[:2000], summary, log=log, evidence_ids=[report_id], tests=tests
            )
        return CheckResult(PASSED, None, summary, log=log, evidence_ids=[report_id], tests=tests)

    @staticmethod
    def _environment(
        suite: TestSuite, cfg: dict[str, Any], job_envs: dict[str, Environment]
    ) -> Environment:
        name = suite.environment or cfg.get("environment")
        if name is None:
            return Environment("default")
        env = suite.environments.get(str(name)) or job_envs.get(str(name))
        if env is None:
            raise ConfigError(f"suite '{suite.name}' references unknown environment '{name}'")
        return env

    def _run_step(
        self,
        client: CheckedClient,
        target: ResolvedTarget,
        env: Environment,
        step: Step,
        variables: dict[str, Any],
        node: str,
        source: str,
    ) -> tuple[TestResult, dict[str, Any]]:
        try:
            params = substitute(step.params, variables)
        except ConfigError as exc:
            rec: dict[str, Any] = {"step": step.name, "error": str(exc)}
            return TestResult(node, step.name, "failed", 0, source, f"configuration: {exc}"), rec
        base = env.base_url or target.base_url
        path = str(params["path"])
        url = (
            path
            if path.startswith(("http://", "https://"))
            else base.rstrip("/") + "/" + path.lstrip("/")
        )
        headers = {**env.headers, **(params.get("headers") or {})}
        params = {**params, "headers": headers}
        body = params.get("body")
        try:
            ex = client.request(
                str(params["method"]),
                url,
                headers=headers,
                content=body.encode("utf-8") if isinstance(body, str) else None,
                json_body=params.get("json"),
                timeout_ms=step.timeout_ms,
                follow_redirects=bool(params.get("follow_redirects", True)),
            )
        except TargetBlocked as exc:
            rec = _exchange_record(step, params, url, None)
            rec["blocked"] = {"reason": exc.reason, "detail": exc.detail}
            return TestResult(
                node,
                step.name,
                "failed",
                0,
                source,
                f"refused by egress policy ({exc.reason}): {exc.detail}",
            ), rec
        except httpx.TimeoutException:
            rec = _exchange_record(step, params, url, None)
            rec["timed_out_after_ms"] = step.timeout_ms
            return TestResult(
                node,
                step.name,
                "timed_out",
                step.timeout_ms,
                source,
                f"no response within {step.timeout_ms} ms",
            ), rec
        except httpx.HTTPError as exc:
            rec = _exchange_record(step, params, url, None)
            rec["transport_error"] = type(exc).__name__
            return TestResult(
                node,
                step.name,
                "failed",
                0,
                source,
                f"transport error: {type(exc).__name__}: {str(exc)[:200]}",
            ), rec
        rec = _exchange_record(step, params, url, ex)
        outcomes: list[dict[str, Any]] = []
        failures: list[str] = []
        for a in step.expect:
            try:
                evaluate(a.kind, substitute(a.params, variables), ex)
                outcomes.append({"assertion": a.describe(), "passed": True})
            except AssertionFailed as exc:
                outcomes.append({"assertion": a.describe(), "passed": False, "detail": str(exc)})
                failures.append(str(exc))
            except ConfigError as exc:
                outcomes.append({"assertion": a.describe(), "passed": False, "detail": str(exc)})
                failures.append(f"configuration: {exc}")
        rec["assertions"] = outcomes
        if not failures:
            for name, path_expr in step.capture.items():
                try:
                    value = resolve(ex.json(), path_expr)
                except (ValueError, JsonPathError) as exc:
                    failures.append(f"capture {name}: {exc}")
                    continue
                if value is MISSING:
                    failures.append(f"capture {name}: {path_expr} is missing")
                else:
                    variables[name] = value
            rec["captured"] = sorted(step.capture)
        if failures:
            return TestResult(
                node, step.name, "failed", ex.elapsed_ms, source, "; ".join(failures)[:4000]
            ), rec
        return TestResult(node, step.name, "passed", ex.elapsed_ms, source), rec
