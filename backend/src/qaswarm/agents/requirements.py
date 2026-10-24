"""AG-02 Requirements Analysis Agent.

Deterministic adapter: turns supplied requirement texts and configured API checks into traceable
scenarios with stable ids, priorities and expected oracles. When an LLM is configured it may
propose additional scenarios, which are validated and marked ``derived_by: llm``; every scenario
must still reference a supplied requirement, otherwise it is dropped and counted.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Literal

from pydantic import Field

from qaswarm.agents.base import AgentContext, AgentOutputModel, AgentResult, AgentTaskInput
from qaswarm.domain.enums import AgentKind

_PRIORITY_HINTS = (
    ("P0", re.compile(r"\b(must|shall|critical|security|authori[sz]|never)\b", re.I)),
    ("P1", re.compile(r"\b(should|important|validate|reject|error)\b", re.I)),
)


class Scenario(AgentOutputModel):
    id: str
    title: str
    priority: Literal["P0", "P1", "P2"]
    requirement_ref: str
    oracle: str
    test_type: Literal["api", "functional", "manual"]
    derived_by: Literal["deterministic", "llm"] = "deterministic"


class RequirementsOutput(AgentOutputModel):
    requirements: list[dict[str, str]]
    scenarios: list[Scenario]
    gaps: list[str] = Field(default_factory=list)
    dropped_llm_proposals: int = 0


def _priority(text: str) -> Literal["P0", "P1", "P2"]:
    for prio, pattern in _PRIORITY_HINTS:
        if pattern.search(text):
            return prio  # type: ignore[return-value]
    return "P2"


def _req_id(index: int, text: str) -> str:
    return f"REQ-{index + 1:03d}-{hashlib.sha256(text.encode()).hexdigest()[:6]}"


class RequirementsAnalysisAgent:
    agent_id = "AG-02"
    name = "Requirements Analysis Agent"
    kind = AgentKind.DETERMINISTIC_WITH_LLM
    task_types = ("requirements.analyze",)
    output_model = RequirementsOutput

    def run(self, task: AgentTaskInput, ctx: AgentContext) -> AgentResult:
        raw_reqs: list[str] = [
            str(r).strip() for r in task.inputs.get("requirements", []) if str(r).strip()
        ]
        api_checks: list[dict[str, Any]] = list(task.inputs.get("api_checks", []))
        requirements = [{"id": _req_id(i, r), "text": r} for i, r in enumerate(raw_reqs)]
        scenarios: list[Scenario] = []
        gaps: list[str] = []

        for req in requirements:
            scenarios.append(
                Scenario(
                    id=f"SCN-{req['id']}",
                    title=req["text"][:200],
                    priority=_priority(req["text"]),
                    requirement_ref=req["id"],
                    oracle="manual acceptance (no executable oracle supplied)",
                    test_type="manual",
                )
            )
        for i, check in enumerate(api_checks):
            method = str(check.get("method", "GET")).upper()
            url = str(check.get("url", ""))
            expected = check.get("expected_status", 200)
            ref = str(
                check.get("requirement_ref")
                or (requirements[0]["id"] if requirements else "API-CHECKS")
            )
            scenarios.append(
                Scenario(
                    id=f"SCN-API-{i + 1:03d}",
                    title=f"{method} {url} responds {expected}",
                    priority="P0" if str(check.get("priority", "")).upper() == "P0" else "P1",
                    requirement_ref=ref,
                    oracle=f"HTTP status == {expected}",
                    test_type="api",
                )
            )
        if not requirements and not api_checks:
            gaps.append("No requirements or API checks were supplied; nothing traceable to plan.")
        if requirements and not api_checks:
            gaps.append(
                "Requirements have no executable oracle in this build; they are recorded as manual scenarios."
            )

        adapter, model_ref, tin, tout, dropped = "deterministic", None, 0, 0, 0
        if ctx.llm is not None and getattr(ctx.llm, "is_llm", False) and requirements:
            proposed, completion = ctx.llm.complete_json(
                "Propose test scenarios for these requirements as JSON "
                '{"scenarios":[{"title","requirement_ref","priority"}]}:\n'
                + "\n".join(f"{r['id']}: {r['text']}" for r in requirements),
                schema_hint={
                    "scenarios": [
                        {"title": "string", "requirement_ref": "string", "priority": "P0|P1|P2"}
                    ]
                },
            )
            adapter, model_ref, tin, tout = (
                ctx.llm.name,
                completion.model_ref,
                completion.tokens_in,
                completion.tokens_out,
            )
            known = {r["id"] for r in requirements}
            for j, item in enumerate(proposed.get("scenarios", []) or []):
                ref = str(item.get("requirement_ref", ""))
                prio = str(item.get("priority", "P2")).upper()
                if (
                    ref not in known
                    or prio not in ("P0", "P1", "P2")
                    or not str(item.get("title", "")).strip()
                ):
                    dropped += 1
                    continue
                scenarios.append(
                    Scenario(
                        id=f"SCN-LLM-{j + 1:03d}",
                        title=str(item["title"])[:200],
                        priority=prio,
                        requirement_ref=ref,
                        oracle="proposed by local model; needs a human-defined oracle",
                        test_type="manual",
                        derived_by="llm",
                    )
                )

        payload = RequirementsOutput(
            requirements=requirements, scenarios=scenarios, gaps=gaps, dropped_llm_proposals=dropped
        ).model_dump(mode="json")
        return AgentResult(
            schema_name="requirements_analysis",
            schema_version="1.0",
            payload=payload,
            adapter=adapter,
            agent_kind=AgentKind.LLM_ASSISTED if model_ref else AgentKind.DETERMINISTIC,
            model_ref=model_ref,
            tokens_in=tin,
            tokens_out=tout,
            warnings=gaps,
        )
