"""Registry of implemented agents and the full catalogue (implemented or planned)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from qaswarm.agents.api_testing import ApiTestingAgent
from qaswarm.agents.base import Agent
from qaswarm.agents.evidence import EvidenceAnalysisAgent
from qaswarm.agents.functional import FunctionalTestingAgent
from qaswarm.agents.reporting import ReportingAgent
from qaswarm.agents.requirements import RequirementsAnalysisAgent
from qaswarm.domain.enums import AgentKind


@dataclass(frozen=True)
class AgentInfo:
    agent_id: str
    name: str
    kind: AgentKind
    stage: str
    implemented: bool
    adapter: str
    planned_slice: str | None = None
    task_types: tuple[str, ...] = ()


_AGENTS: tuple[Any, ...] = (
    RequirementsAnalysisAgent(),
    FunctionalTestingAgent(),
    ApiTestingAgent(),
    EvidenceAnalysisAgent(),
    ReportingAgent(),
)
_IMPLEMENTED: dict[str, Agent] = {a.agent_id: a for a in _AGENTS}

_BY_TASK_TYPE: dict[str, Agent] = {t: a for a in _IMPLEMENTED.values() for t in a.task_types}


def get_agent(task_type: str) -> Agent | None:
    return _BY_TASK_TYPE.get(task_type)


def registered_agents() -> list[Agent]:
    return list(_IMPLEMENTED.values())


AGENT_CATALOGUE: tuple[AgentInfo, ...] = (
    AgentInfo(
        "AG-01",
        "Orchestrator Agent",
        AgentKind.DETERMINISTIC,
        "planning",
        True,
        "deterministic planner (qaswarm.workflow.orchestrator)",
    ),
    AgentInfo(
        "AG-02",
        "Requirements Analysis Agent",
        AgentKind.DETERMINISTIC_WITH_LLM,
        "planning",
        True,
        "deterministic; optional local LLM proposals",
        task_types=("requirements.analyze",),
    ),
    AgentInfo(
        "AG-03",
        "Functional Testing Agent",
        AgentKind.DETERMINISTIC,
        "functional_and_api_testing",
        True,
        "deterministic; reports skipped until an execution engine exists (1c)",
        task_types=("functional.execute",),
    ),
    AgentInfo(
        "AG-04",
        "API Testing Agent",
        AgentKind.DETERMINISTIC,
        "functional_and_api_testing",
        True,
        "deterministic HTTP checker, local allow-list",
        task_types=("api.check",),
    ),
    AgentInfo(
        "AG-05",
        "Security Testing Agent",
        AgentKind.DETERMINISTIC_WITH_LLM,
        "security_testing",
        False,
        "not implemented",
        planned_slice="2a",
    ),
    AgentInfo(
        "AG-06",
        "Performance Testing Agent",
        AgentKind.DETERMINISTIC_WITH_LLM,
        "performance_testing",
        False,
        "not implemented",
        planned_slice="3b",
    ),
    AgentInfo(
        "AG-07",
        "Mutation Testing Agent",
        AgentKind.DETERMINISTIC_WITH_LLM,
        "mutation_testing",
        False,
        "not implemented",
        planned_slice="3c",
    ),
    AgentInfo(
        "AG-08",
        "Evidence and Defect Analysis Agent",
        AgentKind.DETERMINISTIC,
        "evidence_correlation_and_triage",
        True,
        "deterministic correlator",
        task_types=("evidence.correlate",),
    ),
    AgentInfo(
        "AG-09",
        "Patch Proposal Agent",
        AgentKind.LLM_ASSISTED,
        "patch_proposal",
        False,
        "not implemented",
        planned_slice="3d",
    ),
    AgentInfo(
        "AG-10",
        "Independent Verification Agent",
        AgentKind.DETERMINISTIC_WITH_LLM,
        "independent_verification",
        False,
        "not implemented",
        planned_slice="3d",
    ),
    AgentInfo(
        "AG-11",
        "QA Report Agent",
        AgentKind.DETERMINISTIC,
        "quality_gates_and_reporting",
        True,
        "deterministic aggregator; no LLM narrative",
        task_types=("report.build",),
    ),
)
