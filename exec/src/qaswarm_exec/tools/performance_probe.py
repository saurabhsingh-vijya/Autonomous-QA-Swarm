"""Bounded performance probe (phase 4): a closed-loop GET workload with hard caps.

This is **not** a load test. It issues at most ``max_requests`` read-only ``GET``/``HEAD`` requests
with at most ``concurrency`` workers for at most ``duration_seconds`` against configured paths of
an authorised target and reports latency percentiles, throughput and error rate. Every limit is
configurable per job and clamped by worker caps (``AQS_EXEC_PERF_MAX_*``). Profiles: ``smoke``
(≤ 50 requests, 2 workers, ≤ 10 s) and ``baseline`` (≤ 200 requests, 5 workers, ≤ 30 s), inside
the design's envelopes (FR-027). The probe stops early on cancellation, on the wall clock and when
the error rate exceeds the abort threshold, so it never produces uncontrolled load.
"""

from __future__ import annotations

import json
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx

from qaswarm_exec import __version__
from qaswarm_exec.targets import ResolvedTarget, TargetBlocked
from qaswarm_exec.targets.http import CheckedClient
from qaswarm_exec.targets.local_app import LocalTargetError
from qaswarm_exec.testing.redact import redact_url
from qaswarm_exec.tools.base import ERROR, FAILED, PASSED, CheckContext, CheckResult, TestResult
from qaswarm_exec.tools.targeted import (
    blocked_result,
    engine_config,
    local_target_error,
    open_target,
    percentiles,
)

PROFILE_DEFAULTS: dict[str, dict[str, int]] = {
    "smoke": {"max_requests": 50, "concurrency": 2, "duration_seconds": 10},
    "baseline": {"max_requests": 200, "concurrency": 5, "duration_seconds": 30},
}
HARD_CAPS: dict[str, int] = {
    "perf_max_requests": 500,
    "perf_max_concurrency": 10,
    "perf_max_duration_seconds": 60,
}
MAX_PATHS = 10
MAX_SAMPLES_KEPT = 1000
ABORT_ERROR_RATE = 0.5  # stop early once half of the first 20+ requests failed
REQUEST_TIMEOUT_MS = 10_000


def _clamp(value: Any, default: int, cap: int) -> int:
    try:
        n = int(value) if value is not None else default
    except (TypeError, ValueError):
        n = default
    return max(1, min(n, cap))


def effective_limits(cfg: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    profile = str(cfg.get("profile", "smoke")).lower()
    defaults = PROFILE_DEFAULTS[profile]
    caps = {k: _clamp(settings.get(k), v, v) for k, v in HARD_CAPS.items()}
    return {
        "profile": profile,
        "max_requests": _clamp(
            cfg.get("max_requests"), defaults["max_requests"], caps["perf_max_requests"]
        ),
        "concurrency": _clamp(
            cfg.get("concurrency"), defaults["concurrency"], caps["perf_max_concurrency"]
        ),
        "duration_seconds": _clamp(
            cfg.get("duration_seconds"),
            defaults["duration_seconds"],
            caps["perf_max_duration_seconds"],
        ),
        "caps": caps,
    }


class PerformanceProbeEngine:
    engine_id = "performance_probe"
    display_name = "Performance probe (bounded, read-only)"
    executes_repository_code = False

    def tool_version(self) -> str:
        return f"qaswarm_exec {__version__} httpx {httpx.__version__}"

    def run(self, ctx: CheckContext) -> CheckResult:
        cfg = engine_config(ctx)
        profile = str(cfg.get("profile", "smoke")).lower()
        if profile not in PROFILE_DEFAULTS:
            return CheckResult(
                ERROR,
                f"unsupported performance profile '{profile}' for this engine",
                {},
                exit_code=None,
            )
        limits = effective_limits(cfg, ctx.settings)
        paths = [str(p) for p in cfg.get("paths") or ["/health"]][:MAX_PATHS]
        method = str(cfg.get("method", "GET")).upper()
        if method not in ("GET", "HEAD"):
            return CheckResult(
                ERROR, "performance probe only issues GET or HEAD requests", {}, exit_code=None
            )
        raw_thresholds = cfg.get("thresholds")
        thresholds: dict[str, Any] = (
            dict(raw_thresholds) if isinstance(raw_thresholds, dict) else {}
        )
        try:
            with open_target(ctx) as target:
                return self._run(ctx, target, limits, paths, method, thresholds)
        except TargetBlocked as exc:
            return blocked_result(exc)
        except LocalTargetError as exc:
            return local_target_error(exc)

    def _run(
        self,
        ctx: CheckContext,
        target: ResolvedTarget,
        limits: dict[str, Any],
        paths: list[str],
        method: str,
        thresholds: dict[str, Any],
    ) -> CheckResult:
        lock = threading.Lock()
        issued = 0
        samples: dict[str, list[int]] = {p: [] for p in paths}
        statuses: Counter[int] = Counter()
        errors: Counter[str] = Counter()
        stop = threading.Event()
        deadline = time.monotonic() + limits["duration_seconds"]
        started = time.perf_counter()
        aborted: str | None = None
        total_done = 0
        total_errors = 0

        def take() -> str | None:
            nonlocal issued
            with lock:
                if issued >= limits["max_requests"] or stop.is_set() or time.monotonic() > deadline:
                    return None
                if ctx.cancel.is_set():
                    stop.set()
                    return None
                path = paths[issued % len(paths)]
                issued += 1
                return path

        def worker() -> None:
            nonlocal total_done, total_errors, aborted
            with CheckedClient(target.policy, timeout_ms=REQUEST_TIMEOUT_MS) as client:
                while (path := take()) is not None:
                    t0 = time.perf_counter()
                    try:
                        ex = client.request(method, target.url(path), timeout_ms=REQUEST_TIMEOUT_MS)
                        elapsed = int((time.perf_counter() - t0) * 1000)
                        with lock:
                            statuses[ex.status] += 1
                            total_done += 1
                            if ex.status >= 500:
                                total_errors += 1
                            if len(samples[path]) < MAX_SAMPLES_KEPT:
                                samples[path].append(elapsed)
                    except TargetBlocked as exc:
                        with lock:
                            errors[f"blocked:{exc.reason}"] += 1
                            total_done += 1
                            total_errors += 1
                            aborted = f"egress policy refused {exc.host} ({exc.reason})"
                            stop.set()
                    except httpx.HTTPError as exc:
                        with lock:
                            errors[type(exc).__name__] += 1
                            total_done += 1
                            total_errors += 1
                    with lock:
                        if (
                            total_done >= 20
                            and total_errors / total_done > ABORT_ERROR_RATE
                            and not stop.is_set()
                        ):
                            aborted = f"error rate {total_errors / total_done:.0%} exceeded {ABORT_ERROR_RATE:.0%}"
                            stop.set()

        with ThreadPoolExecutor(max_workers=limits["concurrency"]) as pool:
            for _ in range(limits["concurrency"]):
                pool.submit(worker)
        wall_ms = int((time.perf_counter() - started) * 1000)
        all_samples = [s for lst in samples.values() for s in lst]
        pct = percentiles(all_samples)
        error_rate = (total_errors / total_done) if total_done else 1.0
        metrics = {
            "requests": total_done,
            "successful": total_done - total_errors,
            "errors": total_errors,
            "error_rate": round(error_rate, 4),
            "wall_ms": wall_ms,
            "throughput_rps": round(total_done / (wall_ms / 1000), 2) if wall_ms else 0.0,
            "latency_ms": {
                **pct,
                "min": min(all_samples) if all_samples else 0,
                "max": max(all_samples) if all_samples else 0,
                "mean": round(sum(all_samples) / len(all_samples), 1) if all_samples else 0,
            },
            "status_codes": {str(k): v for k, v in sorted(statuses.items())},
            "transport_errors": dict(errors),
        }
        per_path = {p: {**percentiles(s), "count": len(s)} for p, s in samples.items()}
        violations: list[str] = []
        if "p95_ms" in thresholds and pct["p95"] > int(thresholds["p95_ms"]):
            violations.append(f"p95 {pct['p95']} ms > {thresholds['p95_ms']} ms")
        if "p99_ms" in thresholds and pct["p99"] > int(thresholds["p99_ms"]):
            violations.append(f"p99 {pct['p99']} ms > {thresholds['p99_ms']} ms")
        if "error_rate" in thresholds and error_rate > float(thresholds["error_rate"]):
            violations.append(
                f"error rate {error_rate:.2%} > {float(thresholds['error_rate']):.2%}"
            )
        if error_rate >= ABORT_ERROR_RATE:
            violations.append(f"error rate {error_rate:.0%} ≥ {ABORT_ERROR_RATE:.0%}")
        report = {
            "engine": self.engine_id,
            "note": "Bounded closed-loop probe, not a load test. Limits are clamped by worker caps.",
            "target": {
                "kind": target.kind,
                "base_url": redact_url(target.base_url),
                "target_id": target.target_id,
            },
            "limits": limits,
            "paths": paths,
            "method": method,
            "thresholds": thresholds,
            "aborted": aborted,
            "metrics": metrics,
            "per_path": per_path,
            "violations": violations,
        }
        report_id = ctx.evidence.put(
            kind="performance_report",
            label=f"Performance probe report ({limits['profile']})",
            media_type="application/json",
            content=json.dumps(report, indent=1).encode(),
        )
        tests = [
            TestResult(
                f"perf::{p}",
                p,
                "failed" if violations else "passed",
                per_path[p]["p95"],
                None,
                "; ".join(violations) if violations else None,
            )
            for p in paths
        ]
        summary = {
            "profile": limits["profile"],
            "requests": total_done,
            "error_rate": metrics["error_rate"],
            "p50_ms": pct["p50"],
            "p95_ms": pct["p95"],
            "p99_ms": pct["p99"],
            "throughput_rps": metrics["throughput_rps"],
            "aborted": aborted,
            "limits": {k: limits[k] for k in ("max_requests", "concurrency", "duration_seconds")},
        }
        log = (
            f"profile={limits['profile']} requests={total_done} errors={total_errors} "
            f"p50={pct['p50']}ms p95={pct['p95']}ms p99={pct['p99']}ms rps={metrics['throughput_rps']}\n"
            + (f"aborted: {aborted}\n" if aborted else "")
        )
        if total_done == 0:
            return CheckResult(
                ERROR,
                "no request completed",
                summary,
                log=log,
                evidence_ids=[report_id],
                tests=tests,
                exit_code=None,
            )
        if violations:
            return CheckResult(
                FAILED,
                "; ".join(violations),
                summary,
                log=log,
                evidence_ids=[report_id],
                tests=tests,
            )
        return CheckResult(PASSED, None, summary, log=log, evidence_ids=[report_id], tests=tests)
