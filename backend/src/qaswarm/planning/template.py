"""Deterministic template plan: profiles → task DAG.

Task types the Execution Service leases: ``env_prepare`` (fetch the pinned snapshot) and
``check`` (one check engine run). Every check depends on ``env_prepare``. The plan contains no
LLM output and no approval-gated work; Deep security and performance above Smoke produce a
warning instead of tasks because their approvals (HA-02/HA-03) arrive in later slices.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from qaswarm.db.models import Job

ENV_PREPARE = "env_prepare"
CHECK = "check"
CRITICAL_TASK_TYPES: frozenset[str] = frozenset({ENV_PREPARE})

# engine_id → (stage, task priority). Higher priority leases first.
ENGINE_STAGES: dict[str, tuple[str, int]] = {
    "snapshot_integrity": ("environment_preparation", 90),
    "python_syntax": ("functional_and_api_testing", 70),
    "pytest": ("baseline_run", 80),
    "secret_scan": ("security_testing", 60),
}


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


def build_template_plan(job: Job, repository_url: str, provider: str) -> TemplatePlan:
    engines, warnings = _engines_for(job.profiles)
    source = {
        "repository_url": repository_url,
        "provider": provider,
        "ref": job.ref,
        "commit_sha": job.commit_sha,
    }
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
                agent_id={"pytest": "AG-03", "python_syntax": "AG-03", "secret_scan": "AG-05"}.get(
                    engine
                ),
            )
        )
    return TemplatePlan(tasks=tasks, warnings=warnings, engines=engines)
