"""Deterministic template plan: profiles → task DAG.

Task types the Execution Service leases: ``env_prepare`` (fetch the pinned snapshot) and
``check`` (one check engine run). Every check depends on ``env_prepare``. The plan contains no
LLM output and no approval-gated work; Deep security and performance above Smoke/Baseline produce a
warning instead of tasks because their approvals (HA-02/HA-03) arrive in later slices.

Phase 4 adds target-facing engines (``api_tests``, ``browser_tests``, ``security_checks``,
``performance_probe``). They are planned **only** when the job carries a target (a registered
``target_id`` resolved by the scheduler, or the dev-only local fixture target) and the matching
configuration; without that configuration the plan is identical to the phase 2 plan. A rerun job
(``inputs.rerun``) restricts the checks to the selected engines.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from qaswarm.db.models import Job

ENV_PREPARE = "env_prepare"
CHECK = "check"
CRITICAL_TASK_TYPES: frozenset[str] = frozenset({ENV_PREPARE})
LOCAL_FIXTURE_TARGET: dict[str, Any] = {"kind": "local_fixture", "name": "sample-target-app"}

# engine_id → (stage, task priority). Higher priority leases first.
ENGINE_STAGES: dict[str, tuple[str, int]] = {
    "snapshot_integrity": ("environment_preparation", 90),
    "python_syntax": ("functional_and_api_testing", 70),
    "pytest": ("baseline_run", 80),
    "secret_scan": ("security_testing", 60),
    # Phase 4 target-facing engines.
    "api_tests": ("functional_and_api_testing", 66),
    "browser_tests": ("functional_and_api_testing", 64),
    "security_checks": ("security_testing", 56),
    "performance_probe": ("performance_testing", 50),
}
ENGINE_AGENTS: dict[str, str] = {
    "pytest": "AG-03",
    "python_syntax": "AG-03",
    "browser_tests": "AG-03",
    "api_tests": "AG-04",
    "secret_scan": "AG-05",
    "security_checks": "AG-05",
    "performance_probe": "AG-06",
}
TARGET_ENGINES: frozenset[str] = frozenset(
    {"api_tests", "browser_tests", "security_checks", "performance_probe"}
)
KNOWN_ENGINES: frozenset[str] = frozenset(ENGINE_STAGES)


@dataclass(frozen=True)
class PlannedTask:
    key: str  # unique within the plan; used for depends_on wiring
    stage: str
    task_type: str
    inputs: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    priority: int = 0
    agent_id: str | None = None


@dataclass(frozen=True)
class TemplatePlan:
    tasks: list[PlannedTask]
    warnings: list[str]
    engines: list[str]


def _engines_for(profiles: dict[str, Any]) -> tuple[list[str], list[str]]:
    engines: list[str] = ["snapshot_integrity"]
    warnings: list[str] = []
    functional = str(profiles.get("functional", "none"))
    security = str(profiles.get("security", "none"))
    performance = str(profiles.get("performance", "none"))
    if functional != "none":
        engines += ["python_syntax", "pytest"]
    if security != "none":
        engines.append("secret_scan")
    if security == "deep":
        warnings.append("Security Deep (DAST) is Future (Phase 4); only Quick checks were planned.")
    if security in {"quick", "standard"}:
        warnings.append(
            "Security profile: only secret detection runs in this build; SAST, dependency and "
            "IaC scanners arrive in slice 2a."
        )
    if performance != "none":
        warnings.append(
            f"Performance profile '{performance}' was not planned: load generation arrives in "
            "slice 3b."
        )
    return engines, warnings


def requested_activities(job: Job) -> set[str]:
    """Which target activities the job asks for (drives the HA-01 authorization check)."""
    testing = dict((job.inputs or {}).get("testing") or {})
    profiles = job.profiles or {}
    out: set[str] = set()
    if testing.get("api"):
        out.add("api")
    if testing.get("browser"):
        out.add("browser")
    if str(profiles.get("security", "none")) in {"quick", "standard", "deep"}:
        out.add("security")
    if str(profiles.get("performance", "none")) != "none":
        out.add("performance")
    return out


def needs_target(job: Job) -> bool:
    """True when the job carries phase 4 configuration that only makes sense with a target."""
    inputs = job.inputs or {}
    return bool(inputs.get("target_id")) or bool(inputs.get("testing"))


def _target_engines(
    job: Job, target: dict[str, Any], base_warnings: list[str]
) -> tuple[list[tuple[str, dict[str, Any]]], list[str]]:
    testing = dict((job.inputs or {}).get("testing") or {})
    profiles = job.profiles or {}
    security = str(profiles.get("security", "none"))
    performance = str(profiles.get("performance", "none"))
    local = target.get("kind") == "local_fixture"
    allowed = (
        {"api", "browser", "security", "performance"}
        if local
        else set(target.get("allowed_activities", []))
    )
    planned: list[tuple[str, dict[str, Any]]] = []
    warnings = list(base_warnings)

    def refused(activity: str) -> bool:
        if activity in allowed:
            return False
        warnings.append(
            f"Activity '{activity}' is not covered by the target's authorization (HA-01); "
            "its checks were not planned."
        )
        return True

    api = testing.get("api")
    if api is not None and not refused("api"):
        planned.append(("api_tests", dict(api)))
    browser = testing.get("browser")
    if browser is not None and not refused("browser"):
        planned.append(("browser_tests", dict(browser)))
    if security in {"quick", "standard"} and not refused("security"):
        sec_cfg = dict(testing.get("security") or {})
        planned.append(("security_checks", {"profile": security, **sec_cfg}))
        warnings = [w for w in warnings if not w.startswith("Security profile: only secret")]
        warnings.append(
            f"Security profile '{security}': secret detection plus read-only hygiene checks "
            "against the target run in this build; SAST, dependency and IaC scanners arrive in "
            "slice 2a. These checks are informational, not a security assessment."
        )
    if performance in {"smoke", "baseline"} and not refused("performance"):
        if performance == "baseline" and not local:
            warnings.append(
                "Performance Baseline against a registered target requires HA-03, which is not "
                "implemented in this build; no performance task was planned."
            )
        else:
            perf_cfg = dict(testing.get("performance") or {})
            planned.append(("performance_probe", {"profile": performance, **perf_cfg}))
            warnings = [w for w in warnings if not w.startswith("Performance profile")]
            if performance == "baseline":
                warnings.append(
                    "Performance Baseline ran against the worker-local fixture target only "
                    "(HA-03 gating for external targets arrives with the approvals slice)."
                )
    return planned, warnings


def build_template_plan(
    job: Job,
    repository_url: str,
    provider: str,
    *,
    target: dict[str, Any] | None = None,
    fixture_targets: bool = False,
) -> TemplatePlan:
    engines, warnings = _engines_for(job.profiles)
    inputs = job.inputs or {}
    source = {
        "repository_url": repository_url,
        "provider": provider,
        "ref": job.ref,
        "commit_sha": job.commit_sha,
    }
    extra: list[tuple[str, dict[str, Any]]] = []
    if target is None and needs_target(job):
        if inputs.get("target_id"):
            warnings.append("The job's target could not be resolved; target checks were skipped.")
        elif fixture_targets:
            target = dict(LOCAL_FIXTURE_TARGET)
        else:
            warnings.append(
                "Target checks need a registered target (POST /targets + HA-01 attestation) or "
                "the dev-only fixture target (AQS_DEV_FIXTURE_REPOS=true); none was planned."
            )
    if target is not None:
        extra, warnings = _target_engines(job, target, warnings)

    rerun = inputs.get("rerun") if isinstance(inputs.get("rerun"), dict) else None
    if rerun:
        wanted = {str(e) for e in rerun.get("engines", [])}
        unknown = sorted(wanted - KNOWN_ENGINES)
        if unknown:
            warnings.append(f"Rerun requested unknown engine(s): {', '.join(unknown)}.")
        available = set(engines) | {e for e, _ in extra}
        not_planned = sorted((wanted & KNOWN_ENGINES) - available)
        if not_planned:
            warnings.append(
                "Rerun requested engine(s) the profiles do not plan: " + ", ".join(not_planned)
            )
        engines = [e for e in engines if e in wanted]
        extra = [(e, c) for e, c in extra if e in wanted]
        if not engines and not extra:
            warnings.append("Rerun selected no plannable engine; only the snapshot was fetched.")

    tasks: list[PlannedTask] = [
        PlannedTask(
            key=ENV_PREPARE,
            stage="environment_preparation",
            task_type=ENV_PREPARE,
            inputs={"source": source},
            priority=100,
        )
    ]
    for engine in engines:
        stage, priority = ENGINE_STAGES[engine]
        tasks.append(
            PlannedTask(
                key=f"check:{engine}",
                stage=stage,
                task_type=CHECK,
                inputs={"engine": engine, "source": source},
                depends_on=[ENV_PREPARE],
                priority=priority,
                agent_id=ENGINE_AGENTS.get(engine),
            )
        )
    for engine, config in extra:
        stage, priority = ENGINE_STAGES[engine]
        tasks.append(
            PlannedTask(
                key=f"check:{engine}",
                stage=stage,
                task_type=CHECK,
                inputs={"engine": engine, "source": source, "target": target, "config": config},
                depends_on=[ENV_PREPARE],
                priority=priority,
                agent_id=ENGINE_AGENTS.get(engine),
            )
        )
    all_engines = engines + [e for e, _ in extra]
    return TemplatePlan(tasks=tasks, warnings=warnings, engines=all_engines)
