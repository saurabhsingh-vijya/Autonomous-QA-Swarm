"""Combined job plan: Execution Service checks + agent tasks in one DAG.

Repository checks (``env_prepare`` and one ``check`` per engine, leased by the Execution
Service) are planned only when the job has a pinned commit and the Execution Service is
configured (``AQS_EXEC_TOKEN``). Agent tasks are planned from the job's supplied inputs:
requirements analysis, functional and API testing when inputs exist, and always evidence
correlation (AG-08) and the report (AG-11), which read the persisted check runs and test
executions. Evidence soft-depends on every testing task so that a failed or skipped check never
blocks the report; the report hard-depends on nothing but is critical.

The DAG is deterministic for identical inputs (stable keys, stable order, stable hash).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from qaswarm.db.models import Job
from qaswarm.planning.planner import PlanNode, plan_hash, validate_plan
from qaswarm.planning.template import CRITICAL_TASK_TYPES, build_template_plan


@dataclass(frozen=True)
class JobPlanResult:
    nodes: list[PlanNode]
    warnings: list[str]
    engines: list[str]
    problems: list[str] = field(default_factory=list)

    @property
    def plan_hash(self) -> str:
        return plan_hash(self.nodes)


def _has_inputs(inputs: dict[str, Any]) -> bool:
    return bool(inputs.get("requirements")) or bool(inputs.get("api_checks"))


def build_job_plan(
    job: Job,
    *,
    repository_url: str,
    provider: str,
    execution_enabled: bool,
    target: dict[str, Any] | None = None,
    fixture_targets: bool = False,
) -> JobPlanResult:
    inputs: dict[str, Any] = dict(job.inputs or {})
    profiles: dict[str, Any] = dict(job.profiles or {})
    nodes: list[PlanNode] = []
    warnings: list[str] = []
    engines: list[str] = []
    testing_keys: list[str] = []

    # --- Execution Service tasks (phase 2) -------------------------------------------------
    if job.commit_sha and execution_enabled:
        template = build_template_plan(
            job, repository_url, provider, target=target, fixture_targets=fixture_targets
        )
        engines = list(template.engines)
        warnings += template.warnings
        for planned in template.tasks:
            nodes.append(
                PlanNode(
                    key=planned.key,
                    agent_id=planned.agent_id or "EXEC",
                    task_type=planned.task_type,
                    stage=planned.stage,
                    depends_on=tuple(planned.depends_on),
                    critical=planned.task_type in CRITICAL_TASK_TYPES,
                    inputs={**planned.inputs, "priority": planned.priority},
                )
            )
            if planned.task_type == "check":
                testing_keys.append(planned.key)
    elif job.commit_sha and not execution_enabled:
        warnings.append(
            "Repository checks were not planned: the Execution Service is disabled "
            "(AQS_EXEC_TOKEN is not set)."
        )
    else:
        warnings.append(
            "Repository checks were not planned: the ref could not be pinned to a commit."
        )

    # --- Agent tasks (phase 3) --------------------------------------------------------------
    reqs = list(inputs.get("requirements", []))
    checks = list(inputs.get("api_checks", []))
    agent_deps: tuple[str, ...] = ()
    if _has_inputs(inputs):
        nodes.append(
            PlanNode(
                "requirements",
                "AG-02",
                "requirements.analyze",
                "planning",
                critical=True,
                inputs={"requirements": reqs, "api_checks": checks},
            )
        )
        agent_deps = ("requirements",)
        if profiles.get("functional", "none") != "none":
            nodes.append(
                PlanNode(
                    "functional",
                    "AG-03",
                    "functional.execute",
                    "functional_and_api_testing",
                    depends_on=agent_deps,
                )
            )
            testing_keys.append("functional")
        if checks:
            nodes.append(
                PlanNode(
                    "api",
                    "AG-04",
                    "api.check",
                    "functional_and_api_testing",
                    depends_on=agent_deps,
                    inputs={"api_checks": checks},
                )
            )
            testing_keys.append("api")
    else:
        warnings.append(
            "No requirements or API checks were supplied; only repository checks and the "
            "evidence/report agents were planned."
        )

    nodes.append(
        PlanNode(
            "evidence",
            "AG-08",
            "evidence.correlate",
            "evidence_correlation_and_triage",
            depends_on=agent_deps,
            soft_depends_on=tuple(testing_keys),
        )
    )
    nodes.append(
        PlanNode(
            "report",
            "AG-11",
            "report.build",
            "quality_gates_and_reporting",
            depends_on=agent_deps,
            soft_depends_on=("evidence",),
            critical=True,
        )
    )
    problems = validate_plan(nodes)
    return JobPlanResult(nodes=nodes, warnings=warnings, engines=engines, problems=problems)
