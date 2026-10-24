"""Browser testing engine: Playwright for Python + Chromium against an authorised target.

Egress is constrained three ways: all browser traffic (loopback included) goes through the
worker-local :class:`PolicyProxy`, which applies the :class:`TargetPolicy` to every request and
``CONNECT`` at connect time — including redirect targets Chromium follows internally; Playwright
request interception aborts anything outside the authorised host set before it is sent; and
Chromium is launched with ``--host-resolver-rules`` so that only the target host name resolves.
Evidence: screenshots (``image/png``), the console log (``browser_console``, redacted) and a
``browser_test_report`` with per-step timings.

If Playwright is not installed or Chromium is missing, the check ends ``skipped`` with the reason;
it never pretends to have run. The engine never executes repository code.
"""

from __future__ import annotations

import contextlib
import json
import time
from typing import Any
from urllib.parse import urlsplit

from qaswarm_exec import __version__
from qaswarm_exec.targets import ResolvedTarget, TargetBlocked
from qaswarm_exec.targets.local_app import LocalTargetError
from qaswarm_exec.targets.proxy import PolicyProxy
from qaswarm_exec.testing.config import (
    ConfigError,
    Step,
    TestSuite,
    discover_suites,
    load_inline,
    substitute,
)
from qaswarm_exec.testing.redact import redact_text, redact_url
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

MAX_CONSOLE_ENTRIES = 500
MAX_SCREENSHOTS = 50
INSTALL_HINT = (
    "install with `pip install qaswarm-exec[browser]` and `python -m playwright install chromium`"
)


def playwright_status() -> tuple[bool, str]:
    """(available, detail) without launching a browser."""
    try:
        from importlib import metadata

        version = metadata.version("playwright")
    except Exception:
        return False, f"Playwright is not installed; {INSTALL_HINT}"
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except Exception as exc:
        return (
            False,
            f"Playwright {version} cannot be imported ({type(exc).__name__}); {INSTALL_HINT}",
        )
    return True, f"playwright {version}"


class StepFailed(Exception):
    pass


class BrowserTestsEngine:
    engine_id = "browser_tests"
    display_name = "Browser tests (Playwright + Chromium)"
    executes_repository_code = False

    def tool_version(self) -> str:
        ok, detail = playwright_status()
        return f"qaswarm_exec {__version__} {detail if ok else 'playwright unavailable'}"

    def _load(self, ctx: CheckContext, cfg: dict[str, Any]) -> list[TestSuite]:
        suites: list[TestSuite] = []
        inline = cfg.get("inline")
        if isinstance(inline, list) and inline:
            suites += load_inline(inline, kind="browser")
        paths = cfg.get("suites")
        if paths or not suites:
            suites += discover_suites(
                ctx.workspace, kind="browser", paths=[str(p) for p in paths] if paths else None
            )
        return suites

    def run(self, ctx: CheckContext) -> CheckResult:
        cfg = engine_config(ctx)
        try:
            suites = self._load(ctx, cfg)
        except ConfigError as exc:
            return CheckResult(ERROR, f"invalid test configuration: {exc}", {}, exit_code=None)
        if not suites:
            return CheckResult(
                SKIPPED,
                "No browser suites found (.qaswarm/tests/*.yaml with kind: browser, paths or inline).",
                {"suites": 0},
            )
        available, detail = playwright_status()
        if not available:
            return CheckResult(
                SKIPPED, f"Browser testing unavailable: {detail}", {"browser": "unavailable"}
            )
        planned = [
            TestResult(f"{s.name}::{sc.name}::{st.name}", st.name, "skipped", 0, s.source)
            for s in suites
            for sc in s.scenarios
            for st in sc.steps
        ]
        try:
            with open_target(ctx) as target:
                return self._run_suites(ctx, cfg, suites, target)
        except TargetBlocked as exc:
            return blocked_result(exc, planned)
        except LocalTargetError as exc:
            return local_target_error(exc)

    # --------------------------------------------------------------- playwright
    def _run_suites(
        self,
        ctx: CheckContext,
        cfg: dict[str, Any],
        suites: list[TestSuite],
        target: ResolvedTarget,
    ) -> CheckResult:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright

        host = urlsplit(target.base_url).hostname or ""
        args = [f"--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE {host}"]
        proxy = PolicyProxy(target.policy)
        tests: list[TestResult] = []
        console: list[dict[str, Any]] = []
        violations: list[dict[str, str]] = []
        step_records: list[dict[str, Any]] = []
        timings: list[int] = []
        evidence_ids: list[str] = []
        screenshots = 0
        log: list[str] = []
        shots_mode = str(cfg.get("screenshots", "on_failure"))

        def take_screenshot(page: Any, label: str) -> None:
            nonlocal screenshots
            if screenshots >= MAX_SCREENSHOTS:
                return
            screenshots += 1
            png = page.screenshot(full_page=True, type="png")
            evidence_ids.append(
                ctx.evidence.put(
                    kind="screenshot",
                    label=f"Screenshot: {label}"[:200],
                    media_type="image/png",
                    content=png,
                    deterministic=False,
                )
            )

        try:
            with proxy, sync_playwright() as pw:
                try:
                    browser = pw.chromium.launch(
                        headless=True,
                        args=args,
                        proxy={"server": proxy.address, "bypass": "<-loopback>"},
                    )
                except PlaywrightError as exc:
                    return CheckResult(
                        SKIPPED,
                        "Browser testing unavailable: Chromium could not be launched "
                        f"({redact_text(str(exc).splitlines()[0][:200])}); {INSTALL_HINT}",
                        {"browser": "unavailable"},
                    )
                browser_version = browser.version
                context = browser.new_context(
                    ignore_https_errors=False, accept_downloads=False, java_script_enabled=True
                )
                context.set_default_timeout(10_000)

                def route_handler(route: Any, request: Any) -> None:
                    try:
                        target.policy.check_url(request.url)
                    except TargetBlocked as exc:
                        violations.append(
                            {
                                "url": redact_url(request.url),
                                "reason": exc.reason,
                                "detail": exc.detail,
                            }
                        )
                        route.abort("blockedbyclient")
                        return
                    route.continue_()

                context.route("**/*", route_handler)

                def on_response(response: Any) -> None:
                    try:
                        target.policy.check_url(response.url)
                    except TargetBlocked as exc:
                        violations.append(
                            {
                                "url": redact_url(response.url),
                                "reason": exc.reason,
                                "detail": exc.detail,
                                "stage": "response",
                            }
                        )

                def on_console(msg: Any) -> None:
                    if len(console) < MAX_CONSOLE_ENTRIES:
                        console.append(
                            {
                                "type": msg.type,
                                "text": redact_text(msg.text)[:2000],
                                "location": redact_url(str(msg.location.get("url", ""))),
                            }
                        )

                def on_pageerror(err: Any) -> None:
                    if len(console) < MAX_CONSOLE_ENTRIES:
                        console.append({"type": "pageerror", "text": redact_text(str(err))[:2000]})

                for suite in suites:
                    for scenario in suite.scenarios:
                        page = context.new_page()
                        page.on("response", on_response)
                        page.on("console", on_console)
                        page.on("pageerror", on_pageerror)
                        variables: dict[str, Any] = {**suite.data, **scenario.data}
                        failed = False
                        proxied = len(proxy.violations)
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
                            before = len(violations)
                            t0 = time.perf_counter()
                            message: str | None = None
                            status = "passed"
                            try:
                                params = substitute(step.params, variables)
                                self._do_step(
                                    page, target, step, params, variables, take_screenshot
                                )
                                for pv in proxy.violations[proxied:]:
                                    violations.append(
                                        {
                                            "url": redact_url(pv.url),
                                            "reason": pv.reason,
                                            "detail": pv.detail,
                                            "stage": pv.stage,
                                        }
                                    )
                                proxied = len(proxy.violations)
                                if len(violations) > before:
                                    v = violations[-1]
                                    raise StepFailed(
                                        f"navigation refused by egress policy ({v['reason']}): {v['detail']}"
                                    )
                            except StepFailed as exc:
                                status, message = "failed", str(exc)[:4000]
                            except ConfigError as exc:
                                status, message = "failed", f"configuration: {exc}"
                            except PlaywrightError as exc:
                                first = redact_text(str(exc).splitlines()[0][:300])
                                status = (
                                    "timed_out"
                                    if "Timeout" in type(exc).__name__ or "exceeded" in first
                                    else "failed"
                                )
                                message = first
                            duration = int((time.perf_counter() - t0) * 1000)
                            timings.append(duration)
                            if status != "passed":
                                failed = True
                                if shots_mode in ("on_failure", "always"):
                                    with contextlib.suppress(PlaywrightError):
                                        take_screenshot(page, f"{node} (failure)")
                            tests.append(
                                TestResult(node, step.name, status, duration, suite.source, message)
                            )
                            step_records.append(
                                {
                                    "step": node,
                                    "action": step.action,
                                    "status": status,
                                    "duration_ms": duration,
                                    "message": message,
                                    "url": redact_url(page.url),
                                }
                            )
                            log.append(
                                f"{status:>9}  {node}  {duration} ms"
                                + (f"  {message}" if message else "")
                            )
                        page.close()
                context.close()
                browser.close()
        except PlaywrightError as exc:
            return CheckResult(
                ERROR, f"Playwright error: {redact_text(str(exc)[:300])}", {}, exit_code=None
            )

        report = {
            "engine": self.engine_id,
            "browser": f"chromium {browser_version}",
            "target": {
                "kind": target.kind,
                "base_url": redact_url(target.base_url),
                "target_id": target.target_id,
            },
            "suites": [{"name": s.name, "source": s.source, "steps": s.step_count} for s in suites],
            "timings": timing_summary(timings),
            "steps": step_records,
            "policy_violations": violations,
            "console_entries": len(console),
        }
        evidence_ids.append(
            ctx.evidence.put(
                kind="browser_test_report",
                label="Browser test report (redacted)",
                media_type="application/json",
                content=json.dumps(report, indent=1, default=str).encode(),
            )
        )
        evidence_ids.append(
            ctx.evidence.put(
                kind="browser_console",
                label="Browser console log (redacted)",
                media_type="application/json",
                content=json.dumps(console, indent=1).encode(),
                deterministic=False,
            )
        )
        counts = {
            s: sum(1 for t in tests if t.status == s)
            for s in ("passed", "failed", "skipped", "timed_out")
        }
        summary = {
            "suites": len(suites),
            "steps": len(tests),
            **counts,
            "browser": f"chromium {browser_version}",
            "screenshots": screenshots,
            "console_entries": len(console),
            "policy_violations": len(violations),
            "timings": report["timings"],
        }
        text = "\n".join(log) + "\n"
        bad = [t for t in tests if t.status in ("failed", "timed_out")]
        if bad:
            msg = f"{len(bad)} browser step(s) failed: " + "; ".join(
                f"{t.node_id} — {t.message}" for t in bad[:3]
            )
            return CheckResult(
                FAILED, msg[:2000], summary, log=text, evidence_ids=evidence_ids, tests=tests
            )
        return CheckResult(PASSED, None, summary, log=text, evidence_ids=evidence_ids, tests=tests)

    # ------------------------------------------------------------------- steps
    def _do_step(
        self,
        page: Any,
        target: ResolvedTarget,
        step: Step,
        params: dict[str, Any],
        variables: dict[str, Any],
        take_screenshot: Any,
    ) -> None:
        timeout = step.timeout_ms
        action = step.action
        if action == "goto":
            url = target.url(str(params["path"]))
            target.policy.check_url(url)
            page.goto(url, timeout=timeout, wait_until="load")
        elif action == "click":
            page.click(str(params["selector"]), timeout=timeout)
        elif action == "fill":
            page.fill(str(params["selector"]), str(params["value"]), timeout=timeout)
        elif action == "select":
            page.select_option(str(params["selector"]), str(params["value"]), timeout=timeout)
        elif action == "check":
            page.check(str(params["selector"]), timeout=timeout)
        elif action == "press":
            selector = params.get("selector")
            if selector:
                page.press(str(selector), str(params["key"]), timeout=timeout)
            else:
                page.keyboard.press(str(params["key"]))
        elif action == "wait_for":
            page.wait_for_selector(str(params["selector"]), timeout=timeout)
        elif action == "screenshot":
            take_screenshot(page, str(params.get("label", "screenshot")))
        for assertion in step.expect:
            self._assert(page, assertion.kind, substitute(assertion.params, variables), timeout)

    @staticmethod
    def _assert(page: Any, kind: str, params: dict[str, Any], timeout: int) -> None:
        if kind == "title_contains":
            title = page.title()
            if str(params["value"]) not in title:
                raise StepFailed(f"title {title!r} does not contain {params['value']!r}")
        elif kind == "url_contains":
            if str(params["value"]) not in page.url:
                raise StepFailed(
                    f"url {redact_url(page.url)!r} does not contain {params['value']!r}"
                )
        elif kind in ("visible", "hidden"):
            locator = page.locator(str(params["selector"])).first
            visible = locator.is_visible()
            if kind == "visible":
                if not visible:
                    try:
                        locator.wait_for(state="visible", timeout=timeout)
                    except Exception as exc:
                        raise StepFailed(f"{params['selector']} is not visible") from exc
            elif visible:
                raise StepFailed(f"{params['selector']} is visible, expected hidden")
        elif kind in ("text", "value"):
            locator = page.locator(str(params["selector"])).first
            actual = (
                locator.inner_text(timeout=timeout)
                if kind == "text"
                else locator.input_value(timeout=timeout)
            )
            if "equals" in params and actual.strip() != str(params["equals"]):
                raise StepFailed(
                    f"{kind} of {params['selector']} is {actual.strip()!r}, expected {params['equals']!r}"
                )
            if "contains" in params and str(params["contains"]) not in actual:
                raise StepFailed(
                    f"{kind} of {params['selector']} {actual.strip()!r} does not contain {params['contains']!r}"
                )
        elif kind == "count":
            n = page.locator(str(params["selector"])).count()
            if "equals" in params and n != int(params["equals"]):
                raise StepFailed(f"{params['selector']} count is {n}, expected {params['equals']}")
            if "gte" in params and n < int(params["gte"]):
                raise StepFailed(f"{params['selector']} count is {n}, expected ≥ {params['gte']}")
