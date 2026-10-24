"""Agent runtime: typed agent interfaces and the built-in roles for this phase.

Agents receive a defined task with structured input and return a structured, schema-validated
output. They never execute repository code, never hold credentials and never change state
directly; the orchestrator persists their outputs and advances the job.

Roles implemented: AG-01 orchestrator (``qaswarm.workflow.orchestrator``), AG-02 requirements
analysis, AG-03 functional testing (reports honestly that no execution engine exists yet),
AG-04 API testing, AG-08 evidence analysis, AG-11 reporting.
"""

from qaswarm.agents.base import Agent, AgentContext, AgentFailure, AgentResult, AgentTaskInput
from qaswarm.agents.registry import AGENT_CATALOGUE, get_agent, registered_agents

__all__ = [
    "AGENT_CATALOGUE",
    "Agent",
    "AgentContext",
    "AgentFailure",
    "AgentResult",
    "AgentTaskInput",
    "get_agent",
    "registered_agents",
]
