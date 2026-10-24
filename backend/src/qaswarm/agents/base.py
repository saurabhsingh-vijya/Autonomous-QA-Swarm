"""Agent interface shared by every role."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, ValidationError

from qaswarm.domain.enums import AgentKind, ErrorClass


class AgentFailure(Exception):
    """Raised by an agent when it cannot complete its task.

    ``retryable`` failures (provider timeouts, rate limits) go through the task retry budget;
    non-retryable failures end the task ``failed``.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str,
        retryable: bool = False,
        error_class: ErrorClass = ErrorClass.TOOL_ERROR,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.retryable = retryable
        self.error_class = error_class


@dataclass(frozen=True)
class AgentTaskInput:
    """Structured input handed to an agent. Serialisable and hashed for reproducibility."""

    job_id: str
    org_id: str
    task_id: str
    task_type: str
    stage: str
    attempt_no: int
    inputs: dict[str, Any]
    upstream: dict[str, Any] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)

    def sha256(self) -> str:
        body = {
            "job_id": self.job_id,
            "task_type": self.task_type,
            "inputs": self.inputs,
            "upstream": self.upstream,
            "config": self.config,
        }
        return hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()


@dataclass
class AgentContext:
    """Collaborators an agent may use. Agents never receive a database session or secrets."""

    llm: Any | None = None  # an LLMAdapter when configured, otherwise None
    http: Any | None = None  # an HttpChecker for the API Testing Agent
    cancelled: Any | None = None  # zero-argument callable returning True when the job is cancelling


class AgentOutputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


@dataclass
class AgentResult:
    schema_name: str
    schema_version: str
    payload: dict[str, Any]
    adapter: str
    agent_kind: AgentKind
    model_ref: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    evidence: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def sha256(self) -> str:
        return hashlib.sha256(
            json.dumps(self.payload, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()


class Agent(Protocol):
    agent_id: str
    name: str
    kind: AgentKind
    task_types: tuple[str, ...]
    output_model: type[AgentOutputModel]

    def run(self, task: AgentTaskInput, ctx: AgentContext) -> AgentResult: ...


def validate_output(agent: Agent, result: AgentResult) -> AgentResult:
    """Validate a result against the agent's output model; raise a non-retryable failure."""
    try:
        validated = agent.output_model.model_validate(result.payload)
    except ValidationError as exc:
        raise AgentFailure(
            f"{agent.agent_id} output failed schema validation: {exc.errors()[:3]}",
            error_code="E-MODEL-003",
            error_class=ErrorClass.CONTRACT_ERROR,
        ) from exc
    result.payload = validated.model_dump(mode="json")
    return result
