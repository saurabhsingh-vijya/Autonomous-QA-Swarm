"""Safe, read-only security checks against an authorised target (phase 4).

Only ``GET`` requests to configured paths plus one not-found probe. Nothing is fuzzed, injected,
brute-forced or mutated; no state-changing method is ever sent. The checks are **informational
hygiene checks**: security headers, cookie flags, redirect sanity, verbose error bodies and
version disclosure. They are not a vulnerability assessment, a penetration test or a certification
(the design's DAST profile is Future and out of scope here).

Profiles: ``quick`` (headers + cookies on ``/``), ``standard`` (+ configured paths, redirect sanity,
not-found probe). Each check on each path is one ``TestResult`` (``security::<check>::<path>``);
a finding is a ``failed`` result with the detail. The check run ends ``failed`` when any finding of
severity medium or high exists, otherwise ``passed`` with the low-severity findings in the summary.
"""

from __future__ import annotations

import json
import re
import secrets
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

from qaswarm_exec import __version__
from qaswarm_exec.targets import ResolvedTarget, TargetBlocked
from qaswarm_exec.targets.http import CheckedClient, Exchange
from qaswarm_exec.targets.local_app import LocalTargetError
from qaswarm_exec.testing.redact import redact_headers, redact_text, redact_url
from qaswarm_exec.tools.base import (
    ERROR,
    FAILED,
    PASSED,
    CheckContext,
    CheckResult,
    TestResult,
)
from qaswarm_exec.tools.targeted import (
    blocked_result,
    engine_config,
    local_target_error,
    open_target,
)

PROFILES = ("quick", "standard")
MAX_PATHS = 25
DISCLAIMER = (
    "Informational hygiene checks only (read-only GET requests). Not a vulnerability assessment, "
    "penetration test or security certification."
)
_VERBOSE_ERROR = re.compile(
    r"Traceback \(most recent call last\)|\bat [\w$.]+\([\w]+\.java:\d+\)|"
    r"Exception in thread|System\.\w+Exception|<b>Fatal error</b>|PHP (Warning|Notice|Fatal)|"
    r"\bstack ?trace\b|\bORA-\d{5}\b|SQLSTATE\[|psycopg2?\.|sqlalchemy\.exc\.|"
    r"django\.core\.exceptions|werkzeug\.exceptions|\bNullPointerException\b",
    re.IGNORECASE,
)
_VERSIONED = re.compile(r"\d+\.\d+")


@dataclass
class Finding:
    check: str
    severity: str  # high | medium | low
    path: str
    detail: str


def _header(ex: Exchange, name: str) -> str | None:
    return ex.headers.get(name.lower())


def header_checks(ex: Exchange, path: str, *, https: bool) -> list[tuple[str, Finding | None]]:
    """Return ``(check_id, finding-or-None)`` for every header check (so passes are recorded too)."""
    out: list[tuple[str, Finding | None]] = []

    def add(check: str, cond_fail: bool, severity: str, detail: str) -> None:
        out.append((check, Finding(check, severity, path, detail) if cond_fail else None))

    if https:
        hsts = _header(ex, "strict-transport-security")
        add("hsts", hsts is None, "medium", "Strict-Transport-Security header is missing")
    add(
        "x_content_type_options",
        (_header(ex, "x-content-type-options") or "").lower() != "nosniff",
        "low",
        "X-Content-Type-Options: nosniff is missing",
    )
    csp = _header(ex, "content-security-policy")
    xfo = _header(ex, "x-frame-options")
    is_html = "text/html" in (_header(ex, "content-type") or "")
    add(
        "content_security_policy",
        is_html and csp is None,
        "medium",
        "Content-Security-Policy header is missing on an HTML response",
    )
    add(
        "frame_protection",
        is_html and xfo is None and (csp is None or "frame-ancestors" not in csp),
        "medium",
        "Neither X-Frame-Options nor CSP frame-ancestors protects this HTML response",
    )
    add(
        "referrer_policy",
        is_html and _header(ex, "referrer-policy") is None,
        "low",
        "Referrer-Policy header is missing on an HTML response",
    )
    add(
        "permissions_policy",
        is_html and _header(ex, "permissions-policy") is None,
        "low",
        "Permissions-Policy header is missing on an HTML response",
    )
    server = _header(ex, "server") or ""
    powered = _header(ex, "x-powered-by")
    disclosure = []
    if _VERSIONED.search(server):
        disclosure.append(f"Server: {redact_text(server)}")
    if powered:
        disclosure.append(f"X-Powered-By: {redact_text(powered)}")
    add(
        "version_disclosure",
        bool(disclosure),
        "low",
        "Response discloses software versions: " + ", ".join(disclosure),
    )
    return out


def cookie_findings(ex: Exchange, path: str, *, https: bool) -> Finding | None:
    raw = ex.headers.get("set-cookie")
    if not raw:
        return None
    problems: list[str] = []
    for cookie in raw.split("\n"):  # httpx joins multiple Set-Cookie headers with newlines
        attrs = [p.strip().lower() for p in cookie.split(";")]
        name = attrs[0].split("=", 1)[0] if attrs else "?"
        flags = set(attrs[1:])
        missing = []
        if "httponly" not in flags:
            missing.append("HttpOnly")
        if https and "secure" not in flags:
            missing.append("Secure")
        if not any(f.startswith("samesite=") for f in flags):
            missing.append("SameSite")
        if missing:
            problems.append(f"cookie '{name}' lacks {', '.join(missing)}")
    if not problems:
        return None
    return Finding("cookie_flags", "medium", path, "; ".join(problems))


def verbose_error_finding(ex: Exchange, path: str) -> Finding | None:
    text = ex.text()
    m = _VERBOSE_ERROR.search(text)
    if m and (ex.status >= 400 or "Traceback" in m.group(0)):
        return Finding(
            "verbose_error_body",
            "medium",
            path,
            f"HTTP {ex.status} body contains implementation details ({m.group(0)[:40]!r})",
        )
    return None


def redirect_finding(ex: Exchange, path: str, start_scheme: str) -> Finding | None:
    if not ex.hops:
        return None
    schemes = [urlsplit(h.url).scheme for h in ex.hops] + [urlsplit(ex.final_url).scheme]
    if start_scheme == "https" and "http" in schemes:
        return Finding("redirect_sanity", "medium", path, "redirect chain downgrades https → http")
    if len(ex.hops) > 3:
        return Finding("redirect_sanity", "low", path, f"long redirect chain ({len(ex.hops)} hops)")
    return None


class SecurityChecksEngine:
    engine_id = "security_checks"
    display_name = "Security hygiene checks (read-only, non-destructive)"
    executes_repository_code = False

    def tool_version(self) -> str:
        return f"qaswarm_exec {__version__} httpx {httpx.__version__}"

    def run(self, ctx: CheckContext) -> CheckResult:
        cfg = engine_config(ctx)
        profile = str(cfg.get("profile", "quick")).lower()
        if profile not in PROFILES:
            return CheckResult(ERROR, f"unknown security profile '{profile}'", {}, exit_code=None)
        paths = [str(p) for p in cfg.get("paths") or ["/"]][:MAX_PATHS]
        if profile == "quick":
            paths = paths[:1]
        try:
            with open_target(ctx) as target:
                return self._run(ctx, target, profile, paths)
        except TargetBlocked as exc:
            return blocked_result(exc)
        except LocalTargetError as exc:
            return local_target_error(exc)

    def _run(
        self, ctx: CheckContext, target: ResolvedTarget, profile: str, paths: list[str]
    ) -> CheckResult:
        https = urlsplit(target.base_url).scheme == "https"
        tests: list[TestResult] = []
        findings: list[Finding] = []
        observations: list[dict[str, Any]] = []
        log: list[str] = [DISCLAIMER, f"profile={profile} paths={paths}"]

        def record(check: str, path: str, finding: Finding | None, duration: int) -> None:
            node = f"security::{check}::{path}"
            if finding is None:
                tests.append(TestResult(node, check, "passed", duration, None))
            else:
                findings.append(finding)
                tests.append(
                    TestResult(
                        node,
                        check,
                        "failed",
                        duration,
                        None,
                        f"[{finding.severity}] {finding.detail}",
                    )
                )
            log.append(
                f"{'finding' if finding else 'ok':>8}  {node}"
                + (f"  {finding.detail}" if finding else "")
            )

        probe_paths = list(paths)
        if profile == "standard":
            probe_paths.append(f"/qaswarm-probe-{secrets.token_hex(6)}")
        with CheckedClient(target.policy) as client:
            for path in probe_paths:
                if ctx.cancel.is_set():
                    break
                url = target.url(path)
                try:
                    ex = client.request("GET", url, timeout_ms=10_000)
                except TargetBlocked as exc:
                    refused = Finding(
                        "redirect_sanity",
                        "high",
                        path,
                        f"request or redirect refused by egress policy ({exc.reason}): {exc.detail}",
                    )
                    record("redirect_sanity", path, refused, 0)
                    observations.append(
                        {"path": path, "blocked": {"reason": exc.reason, "detail": exc.detail}}
                    )
                    continue
                except httpx.HTTPError as exc:
                    tests.append(
                        TestResult(
                            f"security::reachability::{path}",
                            "reachability",
                            "failed",
                            0,
                            None,
                            f"transport error: {type(exc).__name__}",
                        )
                    )
                    log.append(f"   error  {path} {type(exc).__name__}")
                    continue
                observations.append(
                    {
                        "path": path,
                        "status": ex.status,
                        "final_url": redact_url(ex.final_url),
                        "hops": len(ex.hops),
                        "headers": redact_headers(ex.headers),
                        "elapsed_ms": ex.elapsed_ms,
                    }
                )
                is_probe = path.startswith("/qaswarm-probe-")
                if is_probe:
                    probe_finding: Finding | None = None
                    if ex.status != 404:
                        probe_finding = Finding(
                            "not_found_probe",
                            "low",
                            path,
                            f"unknown path answered HTTP {ex.status} instead of 404",
                        )
                    record("not_found_probe", path, probe_finding, ex.elapsed_ms)
                    record(
                        "verbose_error_body", path, verbose_error_finding(ex, path), ex.elapsed_ms
                    )
                    continue
                for check, finding in header_checks(ex, path, https=https):
                    record(check, path, finding, ex.elapsed_ms)
                record("cookie_flags", path, cookie_findings(ex, path, https=https), ex.elapsed_ms)
                record("verbose_error_body", path, verbose_error_finding(ex, path), ex.elapsed_ms)
                if profile == "standard":
                    record(
                        "redirect_sanity",
                        path,
                        redirect_finding(ex, path, urlsplit(url).scheme),
                        ex.elapsed_ms,
                    )
        by_sev = {s: sum(1 for f in findings if f.severity == s) for s in ("high", "medium", "low")}
        report = {
            "engine": self.engine_id,
            "disclaimer": DISCLAIMER,
            "profile": profile,
            "target": {
                "kind": target.kind,
                "base_url": redact_url(target.base_url),
                "target_id": target.target_id,
            },
            "findings": [f.__dict__ for f in findings],
            "observations": observations,
        }
        report_id = ctx.evidence.put(
            kind="security_report",
            label="Security hygiene report (redacted, informational)",
            media_type="application/json",
            content=json.dumps(report, indent=1).encode(),
        )
        summary = {
            "profile": profile,
            "paths": len(paths),
            "checks": len(tests),
            "findings": len(findings),
            **by_sev,
            "disclaimer": DISCLAIMER,
        }
        serious = [f for f in findings if f.severity in ("high", "medium")]
        if serious:
            msg = (
                f"{len(findings)} finding(s) ({by_sev['high']} high, {by_sev['medium']} medium): "
                + "; ".join(f"{f.check} on {f.path}" for f in serious[:4])
            )
            return CheckResult(
                FAILED,
                msg,
                summary,
                log="\n".join(log) + "\n",
                evidence_ids=[report_id],
                tests=tests,
            )
        return CheckResult(
            PASSED, None, summary, log="\n".join(log) + "\n", evidence_ids=[report_id], tests=tests
        )
