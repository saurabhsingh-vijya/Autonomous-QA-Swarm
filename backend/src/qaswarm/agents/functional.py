"""AG-03 Functional Testing Agent.

There is no sandbox execution engine in this build (slice 1c), and the control plane never runs
repository code. This agent therefore reports exactly that: every functional scenario is recorded
as ``skipped`` with the reason, so coverage gates can see it. It never fabricates a result.
"""

from __future__ import annotations

from typing import Any, Literal

from qaswarm.agents.base import AgentContext, AgentOutputModel, AgentResult, AgentTaskInput
from qaswarm.domain.enums import AgentKind

SKIP_REASON = "No sandbox execution engine is registered in this build (arrives in slice 1c)."


class FunctionalExecution(AgentOutputModel):
    scenario_id: str
    name: str
    status: Literal["skipped"]
    message: str


class FunctionalOutput(AgentOutputModel):
    engine: str
    executions: list[FunctionalExecution]
    summary: dict[str, int]


class FunctionalTestingAgent:
    agent_id = "AG-03"
    name = "Functional Testing Agent"
    kind = AgentKind.DETERMINISTIC
    task_types = ("functional.execute",)
    output_model = FunctionalOutput

    def run(self, task: AgentTaskInput, ctx: AgentContext) -> AgentResult:
        scenarios: list[dict[str, Any]] = [
            s
            for s in task.upstream.get("scenarios", [])
            if s.get("test_type") in ("functional", "manual")
        ]
        executions = [
            FunctionalExecution(
                scenario_id=str(s["id"]),
                name=str(s["title"]),
                status="skipped",
                message=SKIP_REASON,
            )
            for s in scenarios
        ]
        payload = FunctionalOutput(
            engine="none",
            executions=executions,
            summary={"executed": 0, "passed": 0, "failed": 0, "skipped": len(executions)},
        ).model_dump(mode="json")
        return AgentResult(
            schema_name="functional_execution",
            schema_version="1.0",
            payload=payload,
            adapter="deterministic",
            agent_kind=AgentKind.DETERMINISTIC,
            warnings=[SKIP_REASON] if executions else [],
        )
