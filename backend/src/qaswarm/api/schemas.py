"""Request and response models for slice 1a endpoints. Unknown request fields are rejected."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from qaswarm.domain.enums import (
    FunctionalProfile,
    JobState,
    PerformanceProfile,
    RepositoryProvider,
    SecurityProfile,
)

T = TypeVar("T")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ResponseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Paginated(ResponseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None
    limit: int


# ---- Projects -----------------------------------------------------------------------------
class ProjectCreate(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class ProjectUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class ProjectOut(ResponseModel):
    id: str
    org_id: str
    org_name: str = ""
    name: str
    description: str | None
    is_sample: bool
    repository_count: int = 0
    created_at: datetime
    updated_at: datetime
    version: int


# ---- Repositories -------------------------------------------------------------------------
class RepositoryCreate(StrictModel):
    project_id: str = Field(pattern=r"^prj_[0-9A-HJKMNP-TV-Z]{26}$")
    provider: RepositoryProvider
    url: str = Field(min_length=1, max_length=2048)
    default_branch: str | None = Field(default=None, max_length=255)
    credential_ref_id: str | None = Field(default=None, max_length=40)


class RepositoryOut(ResponseModel):
    id: str
    org_id: str
    project_id: str
    provider: str
    url: str
    default_branch: str | None
    validation_status: str
    validation_note: str | None
    language_support: str
    last_pinned_sha: str | None
    credential_ref_id: str | None
    created_at: datetime
    updated_at: datetime
    version: int


# ---- Jobs ---------------------------------------------------------------------------------
class JobProfiles(StrictModel):
    functional: FunctionalProfile = FunctionalProfile.STANDARD
    security: SecurityProfile = SecurityProfile.NONE
    performance: PerformanceProfile = PerformanceProfile.NONE


class JobCreate(StrictModel):
    repository_id: str = Field(pattern=r"^rep_[0-9A-HJKMNP-TV-Z]{26}$")
    ref: str = Field(min_length=1, max_length=255)
    profiles: JobProfiles = Field(default_factory=JobProfiles)
    force_new: bool = False

    @field_validator("ref")
    @classmethod
    def _ref_grammar(cls, value: str) -> str:
        bad = (" ", "..", "~", "^", ":", "?", "*", "[", "\\", "\x7f")
        if value.startswith(("-", "/")) or value.endswith(("/", ".lock", ".")):
            raise ValueError("not a valid git ref name")
        if any(ch in value for ch in bad) or any(ord(c) < 0x20 for c in value):
            raise ValueError("not a valid git ref name")
        return value


class JobLinks(ResponseModel):
    self: str
    events: str


class JobOut(ResponseModel):
    id: str
    display_id: str
    org_id: str
    project_id: str
    repository_id: str
    ref: str
    commit_sha: str | None
    profiles: dict[str, Any]
    state: JobState
    current_stage: str | None
    held_reason: str | None
    force_new: bool
    created_by: str
    deadline_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version: int
    links: JobLinks


class StageProgress(ResponseModel):
    stage: str
    status: str
    note: str | None = None
    tasks: int = 0


class JobDetailOut(JobOut):
    cancel_requested_at: datetime | None
    cancel_reason: str | None
    started_at: datetime | None
    ended_at: datetime | None
    snapshot_sha256: str | None = None
    warnings: list[str] = Field(default_factory=list)
    stages: list[StageProgress]
    task_summary: dict[str, int]
    check_summary: dict[str, int] = Field(default_factory=dict)
    test_summary: dict[str, int] = Field(default_factory=dict)


# ---- Phase 2: tasks, checks, tests, evidence, reports -------------------------------------
class TaskAttemptOut(ResponseModel):
    id: str
    attempt_no: int
    lease_owner: str
    outcome: str
    error_code: str | None
    error_class: str | None
    started_at: datetime | None
    ended_at: datetime | None


class TaskOut(ResponseModel):
    id: str
    job_id: str
    stage: str
    task_type: str
    agent_id: str | None
    state: str
    engine: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    priority: int
    attempt_count: int
    last_error_code: str | None
    last_error_class: str | None
    lease_owner: str | None
    available_at: datetime
    state_changed_at: datetime
    created_at: datetime
    attempts: list[TaskAttemptOut] = Field(default_factory=list)


class CheckRunOut(ResponseModel):
    id: str
    job_id: str
    task_id: str
    attempt_no: int
    worker_run_id: str | None
    engine_id: str
    name: str
    outcome: str
    started_at: datetime
    ended_at: datetime
    duration_ms: int
    failure_message: str | None
    summary: dict[str, Any]
    tool_name: str
    tool_version: str
    executes_repository_code: bool
    log_evidence_id: str | None
    evidence_ids: list[str] = Field(default_factory=list)


class TestExecutionOut(ResponseModel):
    id: str
    job_id: str
    check_run_id: str
    node_id: str
    file: str | None
    name: str
    status: str
    duration_ms: int
    message: str | None
    purpose: str
    provenance: str
    tool_version: str
    commit_sha: str | None


class EvidenceItemOut(ResponseModel):
    id: str
    job_id: str
    task_id: str | None
    worker_run_id: str | None
    kind: str
    label: str
    sha256: str
    size_bytes: int
    media_type: str
    producer: str
    redactions: int
    truncated: bool
    original_bytes: int | None
    deterministic: bool
    created_at: datetime


class EvidenceContentOut(ResponseModel):
    id: str
    media_type: str
    sha256: str
    size_bytes: int
    text: str | None
    truncated_inline: bool


class WorkerRunOut(ResponseModel):
    id: str
    job_id: str
    task_id: str
    worker_id: str
    runtime: str
    isolation: str
    image_digest: str
    limits: dict[str, Any]
    network_policy: str
    exit_code: int | None
    outcome: str | None
    output_bytes: int
    truncated: bool
    started_at: datetime
    ended_at: datetime | None
    destroyed_at: datetime | None


class ReportOut(ResponseModel):
    id: str
    job_id: str
    kind: str
    verdict: str | None
    digest: str
    partial: bool
    created_at: datetime
    updated_at: datetime
    content: dict[str, Any]


class CompareCheck(ResponseModel):
    engine: str
    name: str
    base: str | None
    other: str | None
    delta: str  # improved | regressed | unchanged | added | removed


class CompareTest(ResponseModel):
    node_id: str
    base: str | None
    other: str | None
    delta: str


class CompareJobRef(ResponseModel):
    id: str
    display_id: str
    state: JobState
    ref: str
    commit_sha: str | None
    created_at: datetime


class CompareOut(ResponseModel):
    base: CompareJobRef
    other: CompareJobRef
    same_repository: bool
    same_commit: bool
    checks: list[CompareCheck]
    tests: list[CompareTest]
    check_deltas: dict[str, int]
    test_deltas: dict[str, int]
    test_counts: dict[str, dict[str, int]]


class AuditEventOut(ResponseModel):
    id: str
    seq: int
    occurred_at: datetime
    actor_type: str
    actor_id: str
    actor_role: str | None
    action: str
    subject_type: str
    subject_id: str
    job_id: str | None
    correlation_id: str | None
    details: dict[str, Any]
    prev_hash: str
    hash: str


class CapabilitiesOut(BaseModel):
    version: str
    phase: str
    execution_enabled: bool
    repository_code_execution_allowed: bool
    sandbox: str
    dev_fixture_repos: bool
    embedded_scheduler: bool
    embedded_exec_worker: bool
    engines: list[str]
    environment: str = "dev"
    # Startup configuration warnings (phase 6): dev auth on, fixture repos, unsandboxed execution…
    warnings: list[str] = Field(default_factory=list)
    # Endpoints that return 501 in this build, with their planned slice.
    not_implemented: list[dict[str, str]] = Field(default_factory=list)


class JobCancelRequest(StrictModel):
    reason: str | None = Field(default=None, max_length=1000)


class JobCancelOut(ResponseModel):
    id: str
    state: JobState
    requested_by: str
    requested_at: datetime


# ---- Health -------------------------------------------------------------------------------
class HealthOut(BaseModel):
    status: str
    version: str


class ReadyOut(BaseModel):
    status: str
    version: str
    database: str
