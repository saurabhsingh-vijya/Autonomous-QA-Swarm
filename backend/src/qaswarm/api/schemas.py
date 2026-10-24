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


class ApiCheck(StrictModel):
    method: str = Field(default="GET", pattern=r"^(GET|HEAD|OPTIONS|POST|PUT|PATCH|DELETE)$")
    url: str = Field(min_length=8, max_length=2048)
    expected_status: int = Field(default=200, ge=100, le=599)
    priority: str = Field(default="P1", pattern=r"^P[0-2]$")
    requirement_ref: str | None = Field(default=None, max_length=80)


class JobInputs(StrictModel):
    """Structured inputs the agents work from in this build (no repository intake yet)."""

    requirements: list[str] = Field(default_factory=list, max_length=200)
    api_checks: list[ApiCheck] = Field(default_factory=list, max_length=100)

    @field_validator("requirements")
    @classmethod
    def _non_empty(cls, value: list[str]) -> list[str]:
        cleaned = [v.strip() for v in value if v and v.strip()]
        if any(len(v) > 2000 for v in cleaned):
            raise ValueError("each requirement must be at most 2000 characters")
        return cleaned


class JobCreate(StrictModel):
    repository_id: str = Field(pattern=r"^rep_[0-9A-HJKMNP-TV-Z]{26}$")
    ref: str = Field(min_length=1, max_length=255)
    profiles: JobProfiles = Field(default_factory=JobProfiles)
    inputs: JobInputs = Field(default_factory=JobInputs)
    require_plan_approval: bool = False
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
    require_plan_approval: bool
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


class JobDetailOut(JobOut):
    inputs: dict[str, Any]
    warnings: dict[str, Any]
    report_available: bool = False
    plan_available: bool = False
    cancel_requested_at: datetime | None
    cancel_reason: str | None
    started_at: datetime | None
    ended_at: datetime | None
    stages: list[StageProgress]
    task_summary: dict[str, int]


class PlanApprovalRequest(StrictModel):
    decision: str = Field(pattern=r"^(approve|reject)$")
    reason: str | None = Field(default=None, max_length=1000)


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
