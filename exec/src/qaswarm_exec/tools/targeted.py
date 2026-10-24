"""Shared plumbing for engines that talk to a target (phase 4).

* :func:`open_target` builds the :class:`TargetSession` from the task's ``target`` descriptor and
  the worker settings;
* :func:`blocked_result` turns a policy refusal into an honest ``skipped`` check (the code under
  test was never reached, so it is neither ``passed`` nor ``failed``);
* :func:`percentiles` / :func:`timing_summary` are the common latency statistics.
"""

from __future__ import annotations

import math
from typing import Any

from qaswarm_exec.targets import TargetBlocked, TargetSession
from qaswarm_exec.targets.local_app import LocalTargetError
from qaswarm_exec.tools.base import ERROR, SKIPPED, CheckContext, CheckResult, TestResult


def engine_config(ctx: CheckContext) -> dict[str, Any]:
    cfg = ctx.task.get("inputs", {}).get("config")
    return dict(cfg) if isinstance(cfg, dict) else {}


def open_target(ctx: CheckContext) -> TargetSession:
    descriptor = ctx.task.get("inputs", {}).get("target")
    return TargetSession(
        descriptor if isinstance(descriptor, dict) else None,
        fixtures_dir=ctx.settings.get("fixtures_dir"),
        allow_local=bool(ctx.settings.get("allow_local_targets", False)),
        out_dir=ctx.out_dir,
    )


def blocked_result(exc: TargetBlocked, planned: list[TestResult] | None = None) -> CheckResult:
    message = f"Target refused by the egress policy ({exc.reason}): {exc.detail}"
    tests = [TestResult(t.node_id, t.name, "blocked", 0, t.file, message) for t in (planned or [])]
    return CheckResult(
        SKIPPED,
        message,
        {"blocked": True, "reason": exc.reason, "host": exc.host, "planned_tests": len(tests)},
        log=message + "\n",
        tests=tests,
        exit_code=None,
    )


def local_target_error(exc: LocalTargetError) -> CheckResult:
    return CheckResult(ERROR, f"local fixture target could not start: {exc}", {}, exit_code=None)


def percentiles(samples: list[int], points: tuple[int, ...] = (50, 95, 99)) -> dict[str, int]:
    if not samples:
        return {f"p{p}": 0 for p in points}
    ordered = sorted(samples)
    out: dict[str, int] = {}
    for p in points:
        rank = max(0, min(len(ordered) - 1, math.ceil(p / 100 * len(ordered)) - 1))
        out[f"p{p}"] = ordered[rank]
    return out


def timing_summary(samples: list[int]) -> dict[str, Any]:
    if not samples:
        return {"count": 0}
    return {
        "count": len(samples),
        "min_ms": min(samples),
        "mean_ms": round(sum(samples) / len(samples), 1),
        "max_ms": max(samples),
        **{f"{k}_ms": v for k, v in percentiles(samples).items()},
    }
