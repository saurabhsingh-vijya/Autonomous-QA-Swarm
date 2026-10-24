"""AG-04 API Testing Agent.

Runs configured HTTP checks against targets the local policy allows (loopback hosts by default)
using safe methods only. Each check yields a deterministic result and an HTTP-exchange evidence
record with headers redacted. No repository code is executed.
"""

from __future__ import annotations

import time
from typing import Any, Literal

from pydantic import Field

from qaswarm.agents.base import AgentContext, AgentOutputModel, AgentResult, AgentTaskInput
from qaswarm.domain.enums import AgentKind
from qaswarm.policy.local import PolicyDecision, evaluate_api_check
from qaswarm.telemetry.logging import redact_value

Status = Literal["passed", "failed", "blocked", "timed_out", "infrastructure_error"]


class CheckResult(AgentOutputModel):
    scenario_id: str
    name: str
    method: str
    url: str
    expected_status: int
    observed_status: int | None = None
    status: Status
    duration_ms: int = 0
    message: str | None = None
    evidence_index: int | None = None


class ApiOutput(AgentOutputModel):
    tool: str = "raone-http-checker"
    tool_version: str = "1.0"
    results: list[CheckResult]
    summary: dict[str, int] = Field(default_factory=dict)


class HttpChecker:
    """Thin HTTP client with a test seam (``transport``)."""

    def __init__(self, timeout_seconds: float = 10.0, transport: Any | None = None) -> None:
        self.timeout = timeout_seconds
        self._transport = transport

    def request(self, method: str, url: str) -> tuple[int, dict[str, str], str, int]:
        started = time.monotonic()
        if self._transport is not None:
            status, headers, body = self._transport(method, url)
        else:
            import httpx

            resp = httpx.request(method, url, timeout=self.timeout, follow_redirects=False)
            status, headers, body = resp.status_code, dict(resp.headers), resp.text[:4096]
        return status, headers, body, int((time.monotonic() - started) * 1000)


class ApiTestingAgent:
    agent_id = "AG-04"
    name = "API Testing Agent"
    kind = AgentKind.DETERMINISTIC
    task_types = ("api.check",)
    output_model = ApiOutput

    def run(self, task: AgentTaskInput, ctx: AgentContext) -> AgentResult:
        checks: list[dict[str, Any]] = list(task.inputs.get("api_checks", []))
        allowed_hosts: list[str] = list(
            task.config.get("api_allowed_hosts", ["localhost", "127.0.0.1"])
        )
        checker: HttpChecker = ctx.http or HttpChecker()
        results: list[CheckResult] = []
        evidence: list[dict[str, Any]] = []
        for i, check in enumerate(checks):
            if ctx.cancelled is not None and ctx.cancelled():
                break
            method = str(check.get("method", "GET")).upper()
            url = str(check.get("url", ""))
            expected = int(check.get("expected_status", 200))
            scenario_id = f"SCN-API-{i + 1:03d}"
            name = f"{method} {url} responds {expected}"
            decision: PolicyDecision = evaluate_api_check(method, url, allowed_hosts)
            if not decision.allowed:
                results.append(
                    CheckResult(
                        scenario_id=scenario_id,
                        name=name,
                        method=method,
                        url=url,
                        expected_status=expected,
                        status="blocked",
                        message=decision.reason,
                    )
                )
                continue
            try:
                observed, headers, body, duration = checker.request(method, url)
            except Exception as exc:
                kind = exc.__class__.__name__
                status: Status = "timed_out" if "Timeout" in kind else "infrastructure_error"
                results.append(
                    CheckResult(
                        scenario_id=scenario_id,
                        name=name,
                        method=method,
                        url=url,
                        expected_status=expected,
                        status=status,
                        message=f"{kind} while calling the target (no response captured)",
                    )
                )
                continue
            passed = observed == expected
            evidence.append(
                {
                    "kind": "http_exchange",
                    "producer": "raone-http-checker 1.0",
                    "content": {
                        "request": {"method": method, "url": url},
                        "response": {
                            "status": observed,
                            "headers": redact_value({k.lower(): v for k, v in headers.items()}),
                            "body_excerpt": redact_value(body[:2048]),
                        },
                        "expected": {"status": expected},
                        "duration_ms": duration,
                    },
                }
            )
            results.append(
                CheckResult(
                    scenario_id=scenario_id,
                    name=name,
                    method=method,
                    url=url,
                    expected_status=expected,
                    observed_status=observed,
                    status="passed" if passed else "failed",
                    duration_ms=duration,
                    message=None if passed else f"expected HTTP {expected}, observed {observed}",
                    evidence_index=len(evidence) - 1,
                )
            )
        summary = {
            k: sum(1 for r in results if r.status == k)
            for k in ("passed", "failed", "blocked", "timed_out", "infrastructure_error")
        }
        summary["executed"] = summary["passed"] + summary["failed"]
        payload = ApiOutput(results=results, summary=summary).model_dump(mode="json")
        return AgentResult(
            schema_name="api_check",
            schema_version="1.0",
            payload=payload,
            adapter="deterministic",
            agent_kind=AgentKind.DETERMINISTIC,
            evidence=evidence,
            warnings=[r.message for r in results if r.status == "blocked" and r.message],
        )
