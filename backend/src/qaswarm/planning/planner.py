"""Deterministic template plan for the roles implemented in this phase.

DAG (hard → must succeed, soft → must be terminal):

    requirements.analyze (AG-02, planning)
        ├─hard→ functional.execute (AG-03)      ┐ run in parallel
        └─hard→ api.check          (AG-04)      ┘
    evidence.correlate (AG-08)  soft← functional.execute, api.check
    report.build       (AG-11)  soft← evidence.correlate
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from qaswarm.agents.registry import get_agent


@dataclass(frozen=True)
class PlanNode:
    key: str
    agent_id: str
    task_type: str
    stage: str
    depends_on: tuple[str, ...] = ()
    soft_depends_on: tuple[str, ...] = ()
    critical: bool = False
    inputs: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "agent_id": self.agent_id,
            "task_type": self.task_type,
            "stage": self.stage,
            "depends_on": list(self.depends_on),
            "soft_depends_on": list(self.soft_depends_on),
            "critical": self.critical,
            "inputs": self.inputs,
        }


def build_plan(job_inputs: dict[str, Any], profiles: dict[str, Any]) -> list[PlanNode]:
    reqs = list(job_inputs.get("requirements", []))
    checks = list(job_inputs.get("api_checks", []))
    nodes: list[PlanNode] = [
        PlanNode(
            "requirements",
            "AG-02",
            "requirements.analyze",
            "planning",
            critical=True,
            inputs={"requirements": reqs, "api_checks": checks},
        ),
    ]
    testing: list[str] = []
    if profiles.get("functional", "none") != "none":
        nodes.append(
            PlanNode(
                "functional",
                "AG-03",
                "functional.execute",
                "functional_and_api_testing",
                depends_on=("requirements",),
            )
        )
        testing.append("functional")
    if checks:
        nodes.append(
            PlanNode(
                "api",
                "AG-04",
                "api.check",
                "functional_and_api_testing",
                depends_on=("requirements",),
                inputs={"api_checks": checks},
            )
        )
        testing.append("api")
    nodes.append(
        PlanNode(
            "evidence",
            "AG-08",
            "evidence.correlate",
            "evidence_correlation_and_triage",
            soft_depends_on=tuple(testing),
            depends_on=("requirements",),
        )
    )
    nodes.append(
        PlanNode(
            "report",
            "AG-11",
            "report.build",
            "quality_gates_and_reporting",
            soft_depends_on=("evidence",),
            depends_on=("requirements",),
            critical=True,
        )
    )
    return nodes


def validate_plan(nodes: list[PlanNode]) -> list[str]:
    """Return a list of problems; empty means valid (acyclic, known agents, resolvable deps)."""
    problems: list[str] = []
    keys = {n.key for n in nodes}
    if len(keys) != len(nodes):
        problems.append("duplicate node keys")
    for n in nodes:
        if get_agent(n.task_type) is None:
            problems.append(f"{n.key}: no agent registered for task type {n.task_type}")
        for d in n.depends_on + n.soft_depends_on:
            if d not in keys:
                problems.append(f"{n.key}: unknown dependency {d}")
    # Kahn's algorithm for cycles
    indeg = {n.key: len(n.depends_on) + len(n.soft_depends_on) for n in nodes}
    children: dict[str, list[str]] = {k: [] for k in keys}
    for n in nodes:
        for d in n.depends_on + n.soft_depends_on:
            if d in children:
                children[d].append(n.key)
    ready = [k for k, v in indeg.items() if v == 0]
    seen = 0
    while ready:
        k = ready.pop()
        seen += 1
        for c in children[k]:
            indeg[c] -= 1
            if indeg[c] == 0:
                ready.append(c)
    if seen != len(nodes):
        problems.append("plan contains a cycle")
    return problems


def plan_hash(nodes: list[PlanNode]) -> str:
    body = json.dumps([n.to_dict() for n in nodes], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode()).hexdigest()
