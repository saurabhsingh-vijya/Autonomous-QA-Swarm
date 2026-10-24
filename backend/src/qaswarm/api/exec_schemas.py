"""Request/response models of the narrow internal API used by the Execution Service."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExecModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LeaseRequest(ExecModel):
    worker_id: str = Field(min_length=1, max_length=200)
    task_types: list[str] = Field(min_length=1, max_length=20)
    batch_size: int = Field(default=1, ge=1, le=10)


class LeasedTask(BaseModel):
    task_id: str
    attempt_id: str
    attempt_no: int
    job_id: str
    org_id: str
    job_display_id: str
    stage: str
    task_type: str
    inputs: dict[str, Any]
    lease_expires_at: datetime
    limits: dict[str, Any]
    context: dict[str, Any]


class LeaseResponse(BaseModel):
    tasks: list[LeasedTask]


class HeartbeatRequest(ExecModel):
    worker_id: str


class HeartbeatResponse(BaseModel):
    task_id: str
    state: str
    lease_expires_at: datetime


class WorkerRunCreate(ExecModel):
    worker_id: str
    attempt_id: str | None = None
    runtime: str = Field(max_length=40)
    isolation: str = Field(max_length=20)
    image_digest: str = Field(pattern=r"^sha256:[0-9a-f]{8,64}$")
    limits: dict[str, Any] = Field(default_factory=dict)
    network_policy: str = Field(default="unenforced", max_length=40)


class WorkerRunCreated(BaseModel):
    worker_run_id: str


class WorkerRunDestroyed(ExecModel):
    outcome: str = Field(max_length=30)
    exit_code: int | None = None
    output_bytes: int = Field(default=0, ge=0)
    truncated: bool = False


class EvidenceUpload(ExecModel):
    worker_id: str
    worker_run_id: str | None = None
    kind: str = Field(max_length=40)
    label: str = Field(default="", max_length=200)
    media_type: str = Field(default="text/plain", max_length=80)
    content_base64: str
    deterministic: bool = True
    producer: str = Field(default="qaswarm_exec", max_length=120)


class EvidenceUploaded(BaseModel):
    evidence_id: str
    sha256: str
    size_bytes: int
    redactions: int
    truncated: bool


class CheckRunIn(ExecModel):
    engine_id: str = Field(max_length=80)
    name: str = Field(max_length=200)
    outcome: str
    started_at: datetime
    ended_at: datetime
    duration_ms: int = Field(ge=0)
    failure_message: str | None = Field(default=None, max_length=20000)
    summary: dict[str, Any] = Field(default_factory=dict)
    tool_name: str = Field(max_length=80)
    tool_version: str = Field(max_length=80)
    executes_repository_code: bool = False
    log_evidence_id: str | None = None
    evidence_ids: list[str] = Field(default_factory=list, max_length=1000)


class TestExecutionIn(ExecModel):
    node_id: str = Field(max_length=500)
    file: str | None = Field(default=None, max_length=500)
    name: str = Field(max_length=300)
    status: str
    duration_ms: int = Field(default=0, ge=0)
    message: str | None = Field(default=None, max_length=20000)


class ResultSubmit(ExecModel):
    worker_id: str
    worker_result: dict[str, Any]
    snapshot_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    check_runs: list[CheckRunIn] = Field(default_factory=list, max_length=200)
    test_executions: list[TestExecutionIn] = Field(default_factory=list, max_length=20000)


class FailureSubmit(ExecModel):
    worker_id: str
    error_code: str = Field(max_length=40)
    error_class: str = Field(default="infrastructure_error")
    retryable: bool = True
    kind: str = Field(default="error", pattern=r"^(error|timed_out)$")
    message: str | None = Field(default=None, max_length=20000)


class TaskStateOut(BaseModel):
    task_id: str
    state: str
