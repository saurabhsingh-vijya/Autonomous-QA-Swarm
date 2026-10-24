"""SQLAlchemy 2 models for slice 1a entities.

Organization, Project, Repository, Job, Task, TaskAttempt, AuditEvent, IdempotencyRecord and
OutboxEvent. Every tenant table carries ``org_id`` (row-level security arrives later).
All timestamps are timezone-aware UTC.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from qaswarm.domain.enums import TERMINAL_JOB_STATES


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSONB, datetime: DateTime(timezone=True)}


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow, nullable=False)


class Organization(TimestampMixin, Base):
    __tablename__ = "organizations"
    __table_args__ = (CheckConstraint("id ~ '^org_'", name="ck_organizations_id_prefix"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    settings: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    job_sequence: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)


class Project(TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("org_id", "name", name="uq_projects_org_name"),
        CheckConstraint("id ~ '^prj_'", name="ck_projects_id_prefix"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    gate_config: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    default_profiles: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    archived_at: Mapped[datetime | None]
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    repositories: Mapped[list[Repository]] = relationship(back_populates="project")


class Repository(TimestampMixin, Base):
    __tablename__ = "repositories"
    __table_args__ = (
        UniqueConstraint("org_id", "normalized_url", name="uq_repositories_org_url"),
        CheckConstraint("url LIKE 'https://%'", name="ck_repositories_https_only"),
        CheckConstraint("id ~ '^rep_'", name="ck_repositories_id_prefix"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_url: Mapped[str] = mapped_column(Text, nullable=False)
    default_branch: Mapped[str | None] = mapped_column(String(255))
    last_pinned_sha: Mapped[str | None] = mapped_column(String(40))
    validation_status: Mapped[str] = mapped_column(String(30), nullable=False)
    validation_note: Mapped[str | None] = mapped_column(Text)
    language_support: Mapped[str] = mapped_column(String(30), default="unknown", nullable=False)
    credential_ref_id: Mapped[str | None] = mapped_column(String(40))
    archived_at: Mapped[datetime | None]
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    project: Mapped[Project] = relationship(back_populates="repositories")


class TargetEnvironment(TimestampMixin, Base):
    """Registered non-production target (FR-050). ``kind`` is ``registered`` or ``ephemeral``.

    Tests may run against it only under an unexpired :class:`TargetAuthorization` (HA-01).
    Credentials are never stored here; ``credential_ref_id`` points to the secrets broker.
    """

    __tablename__ = "target_environments"
    __table_args__ = (
        UniqueConstraint("org_id", "project_id", "name", name="uq_targets_project_name"),
        CheckConstraint("id ~ '^tgt_'", name="ck_target_environments_id_prefix"),
        CheckConstraint("kind IN ('registered', 'ephemeral')", name="ck_target_environments_kind"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    environment_type: Mapped[str] = mapped_column(String(30), nullable=False)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    owner: Mapped[str] = mapped_column(String(200), nullable=False)
    network_scope: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    credential_ref_id: Mapped[str | None] = mapped_column(String(40))
    archived_at: Mapped[datetime | None]
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    authorizations: Mapped[list[TargetAuthorization]] = relationship(back_populates="target")


class TargetAuthorization(TimestampMixin, Base):
    """HA-01 attestation that testing the target is permitted (activities, time window)."""

    __tablename__ = "target_authorizations"
    __table_args__ = (
        Index("ix_target_authorizations_target", "target_id", "valid_until"),
        CheckConstraint("id ~ '^tauth_'", name="ck_target_authorizations_id_prefix"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    target_id: Mapped[str] = mapped_column(
        ForeignKey("target_environments.id"), nullable=False, index=True
    )
    attested_by: Mapped[str] = mapped_column(String(200), nullable=False)
    attested_role: Mapped[str] = mapped_column(String(40), nullable=False)
    allowed_activities: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    valid_from: Mapped[datetime] = mapped_column(nullable=False)
    valid_until: Mapped[datetime] = mapped_column(nullable=False)
    revoked_at: Mapped[datetime | None]
    note: Mapped[str | None] = mapped_column(Text)

    target: Mapped[TargetEnvironment] = relationship(back_populates="authorizations")


class Job(TimestampMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("org_id", "display_id", name="uq_jobs_org_display_id"),
        Index(
            "uq_jobs_active_duplicate",
            "repository_id",
            "ref",
            "profile_hash",
            unique=True,
            postgresql_where=text(
                "state NOT IN ("
                + ", ".join(f"'{s.value}'" for s in sorted(TERMINAL_JOB_STATES))
                + ") AND force_new = false"
            ),
        ),
        Index("ix_jobs_org_created", "org_id", "created_at"),
        CheckConstraint("id ~ '^job_'", name="ck_jobs_id_prefix"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    repository_id: Mapped[str] = mapped_column(
        ForeignKey("repositories.id"), nullable=False, index=True
    )
    display_id: Mapped[str] = mapped_column(String(20), nullable=False)
    ref: Mapped[str] = mapped_column(String(255), nullable=False)
    commit_sha: Mapped[str | None] = mapped_column(String(40))
    snapshot_id: Mapped[str | None] = mapped_column(String(40))
    snapshot_sha256: Mapped[str | None] = mapped_column(String(64))
    warnings: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    profiles: Mapped[dict[str, Any]] = mapped_column(nullable=False)
    # Phase 4: optional job inputs: ``target_id``, ``testing`` configuration, ``rerun`` origin.
    inputs: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    profile_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    current_stage: Mapped[str | None] = mapped_column(String(50))
    held_reason: Mapped[str | None] = mapped_column(Text)
    require_plan_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    force_new: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by: Mapped[str] = mapped_column(String(200), nullable=False)
    deadline_at: Mapped[datetime | None]
    cancel_requested_at: Mapped[datetime | None]
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    state_changed_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)
    started_at: Mapped[datetime | None]
    ended_at: Mapped[datetime | None]
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    tasks: Mapped[list[Task]] = relationship(back_populates="job")


class Task(TimestampMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_tasks_idempotency_key"),
        Index("ix_tasks_queue", "state", "available_at"),
        Index("ix_tasks_lease", "state", "lease_expires_at"),
        CheckConstraint("id ~ '^tsk_'", name="ck_tasks_id_prefix"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String(50), nullable=False)
    task_type: Mapped[str] = mapped_column(String(80), nullable=False)
    agent_id: Mapped[str | None] = mapped_column(String(10))
    state: Mapped[str] = mapped_column(String(30), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    depends_on: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    inputs: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    available_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    retry_class: Mapped[str] = mapped_column(String(20), default="transient", nullable=False)
    corrective_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(200))
    lease_expires_at: Mapped[datetime | None]
    last_error_code: Mapped[str | None] = mapped_column(String(40))
    last_error_class: Mapped[str | None] = mapped_column(String(40))
    state_changed_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)

    job: Mapped[Job] = relationship(back_populates="tasks")
    attempts: Mapped[list[TaskAttempt]] = relationship(back_populates="task")


class TaskAttempt(TimestampMixin, Base):
    __tablename__ = "task_attempts"
    __table_args__ = (
        UniqueConstraint("task_id", "attempt_no", name="uq_task_attempts_task_no"),
        CheckConstraint("id ~ '^att_'", name="ck_task_attempts_id_prefix"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    lease_owner: Mapped[str] = mapped_column(String(200), nullable=False)
    lease_expires_at: Mapped[datetime] = mapped_column(nullable=False)
    last_heartbeat_at: Mapped[datetime] = mapped_column(nullable=False)
    outcome: Mapped[str] = mapped_column(String(30), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(40))
    error_class: Mapped[str | None] = mapped_column(String(40))
    started_at: Mapped[datetime | None]
    ended_at: Mapped[datetime | None]

    task: Mapped[Task] = relationship(back_populates="attempts")


class WorkerRun(TimestampMixin, Base):
    """One disposable worker lifecycle reported by the Execution Service (phase 2).

    ``isolation`` records what actually ran: ``process`` (subprocess runtime, not a sandbox) or
    ``none`` (no process was started). gVisor/Docker isolation is not available in this build.
    """

    __tablename__ = "worker_runs"
    __table_args__ = (CheckConstraint("id ~ '^wrk_'", name="ck_worker_runs_id_prefix"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), nullable=False, index=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    attempt_id: Mapped[str | None] = mapped_column(String(40))
    worker_id: Mapped[str] = mapped_column(String(200), nullable=False)
    runtime: Mapped[str] = mapped_column(String(40), nullable=False)
    isolation: Mapped[str] = mapped_column(String(20), nullable=False)
    image_digest: Mapped[str] = mapped_column(String(100), nullable=False)
    limits: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    network_policy: Mapped[str] = mapped_column(String(40), nullable=False, default="unenforced")
    exit_code: Mapped[int | None] = mapped_column(Integer)
    outcome: Mapped[str | None] = mapped_column(String(30))
    output_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    truncated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    started_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)
    ended_at: Mapped[datetime | None]
    destroyed_at: Mapped[datetime | None]


class CheckRun(TimestampMixin, Base):
    """One check executed by a check engine for a task attempt (phase 2)."""

    __tablename__ = "check_runs"
    __table_args__ = (
        Index("ix_check_runs_job_engine", "job_id", "engine_id"),
        CheckConstraint("id ~ '^chk_'", name="ck_check_runs_id_prefix"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), nullable=False, index=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    worker_run_id: Mapped[str | None] = mapped_column(String(40))
    engine_id: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(nullable=False)
    ended_at: Mapped[datetime] = mapped_column(nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    failure_message: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    tool_name: Mapped[str] = mapped_column(String(80), nullable=False)
    tool_version: Mapped[str] = mapped_column(String(80), nullable=False)
    executes_repository_code: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    log_evidence_id: Mapped[str | None] = mapped_column(String(40))
    evidence: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)


class TestExecution(TimestampMixin, Base):
    """One test result normalised to the six design statuses (phase 2)."""

    __tablename__ = "test_executions"
    __table_args__ = (
        Index("ix_test_executions_job_status", "job_id", "status"),
        CheckConstraint("id ~ '^tex_'", name="ck_test_executions_id_prefix"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), nullable=False, index=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), nullable=False)
    check_run_id: Mapped[str | None] = mapped_column(ForeignKey("check_runs.id"))
    worker_run_id: Mapped[str | None] = mapped_column(String(40))
    node_id: Mapped[str] = mapped_column(String(500), default="", server_default="", nullable=False)
    # Agent-produced executions (phase 3): scenario link, type, structured metadata, evidence.
    scenario_id: Mapped[str | None] = mapped_column(String(80))
    test_type: Mapped[str] = mapped_column(
        String(30), default="functional", server_default="functional", nullable=False
    )
    meta: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}", nullable=False)
    tool: Mapped[str] = mapped_column(String(80), default="", server_default="", nullable=False)
    evidence_id: Mapped[str | None] = mapped_column(String(40))
    file: Mapped[str | None] = mapped_column(String(500))
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    message: Mapped[str | None] = mapped_column(Text)
    purpose: Mapped[str] = mapped_column(String(20), default="baseline", nullable=False)
    provenance: Mapped[str] = mapped_column(String(20), default="existing", nullable=False)
    tool_version: Mapped[str] = mapped_column(String(80), nullable=False)
    commit_sha: Mapped[str | None] = mapped_column(String(40))


class EvidenceItem(TimestampMixin, Base):
    """Content-addressed, immutable evidence object metadata (phase 2)."""

    __tablename__ = "evidence_items"
    __table_args__ = (
        Index("ix_evidence_items_sha", "org_id", "sha256"),
        CheckConstraint("id ~ '^evd_'", name="ck_evidence_items_id_prefix"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), nullable=False, index=True)
    task_id: Mapped[str | None] = mapped_column(String(40), index=True)
    worker_run_id: Mapped[str | None] = mapped_column(String(40))
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    # Object in the local evidence store (phase 2); agent evidence may instead be kept inline.
    storage_key: Mapped[str | None] = mapped_column(String(300))
    content: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    redaction_status: Mapped[str] = mapped_column(
        String(20), default="redacted", server_default="redacted", nullable=False
    )
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    media_type: Mapped[str] = mapped_column(String(80), nullable=False)
    producer: Mapped[str] = mapped_column(String(120), nullable=False)
    redactions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    truncated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    original_bytes: Mapped[int | None] = mapped_column(Integer)
    deterministic: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Report(TimestampMixin, Base):
    """Generated job report (JSON source for every other format)."""

    __tablename__ = "reports"
    __table_args__ = (
        UniqueConstraint("job_id", "kind", name="uq_reports_job_kind"),
        CheckConstraint("id ~ '^rpt_'", name="ck_reports_id_prefix"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(30), nullable=False, default="main")
    verdict: Mapped[str | None] = mapped_column(String(30))
    content: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    partial: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    generator: Mapped[str] = mapped_column(
        String(80), default="", server_default="", nullable=False
    )


class AuditEvent(Base):
    """Append-only, hash-chained audit record. Never updated or deleted by the application."""

    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_org_seq", "org_id", "seq"),
        Index("ix_audit_events_subject", "subject_type", "subject_id"),
        CheckConstraint("id ~ '^aud_'", name="ck_audit_events_id_prefix"),
    )

    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(nullable=False)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(200), nullable=False)
    actor_role: Mapped[str | None] = mapped_column(String(40))
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(40), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(40), nullable=False)
    job_id: Mapped[str | None] = mapped_column(String(40), index=True)
    correlation_id: Mapped[str | None] = mapped_column(String(100))
    details: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)


class OutboxEvent(Base):
    """Transactional outbox feeding the SSE stream (same transaction as the state change)."""

    __tablename__ = "outbox_events"
    __table_args__ = (Index("ix_outbox_events_job_seq", "job_id", "seq"),)

    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    job_id: Mapped[str | None] = mapped_column(String(40))
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "principal_id", "endpoint", "idempotency_key", name="uq_idempotency_scope_key"
        ),
        Index("ix_idempotency_expires", "expires_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    principal_id: Mapped[str] = mapped_column(String(200), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(200), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body: Mapped[dict[str, Any]] = mapped_column(nullable=False)
    response_headers: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)


class JobPlan(TimestampMixin, Base):
    __tablename__ = "job_plans"
    __table_args__ = (
        UniqueConstraint("job_id", "revision", name="uq_job_plans_job_revision"),
        CheckConstraint("id ~ '^pln_'", name="ck_job_plans_id_prefix"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), nullable=False, index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(10), default="1.0", nullable=False)
    dag: Mapped[dict[str, Any]] = mapped_column(nullable=False)
    plan_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    approval_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    approved_at: Mapped[datetime | None]
    planner: Mapped[str] = mapped_column(String(40), default="deterministic", nullable=False)


class Approval(TimestampMixin, Base):
    __tablename__ = "approvals"
    __table_args__ = (CheckConstraint("id ~ '^apr_'", name="ck_approvals_id_prefix"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    ha_id: Mapped[str] = mapped_column(String(10), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(40), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    approver_id: Mapped[str] = mapped_column(String(200), nullable=False)
    role_at_decision: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    subject_hash: Mapped[str | None] = mapped_column(String(64))
    expires_at: Mapped[datetime | None]


class AgentOutput(Base):
    """Schema-validated output of one agent task attempt, with provenance."""

    __tablename__ = "agent_outputs"
    __table_args__ = (CheckConstraint("id ~ '^aout_'", name="ck_agent_outputs_id_prefix"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), nullable=False, index=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    agent_id: Mapped[str] = mapped_column(String(10), nullable=False)
    agent_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    adapter: Mapped[str] = mapped_column(String(60), nullable=False)
    model_ref: Mapped[str | None] = mapped_column(String(120))
    schema_name: Mapped[str] = mapped_column(String(60), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(10), nullable=False)
    validation_status: Mapped[str] = mapped_column(String(20), nullable=False)
    input_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    output_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(nullable=False)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)


class Finding(TimestampMixin, Base):
    __tablename__ = "findings"
    __table_args__ = (
        UniqueConstraint("org_id", "display_id", name="uq_findings_org_display_id"),
        Index("ix_findings_org_fingerprint", "org_id", "fingerprint"),
        CheckConstraint("dcs >= 0 AND dcs <= 100", name="ck_findings_dcs_range"),
        CheckConstraint("id ~ '^fnd_'", name="ck_findings_id_prefix"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), nullable=False, index=True)
    display_id: Mapped[str] = mapped_column(String(20), nullable=False)
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    confidence: Mapped[str] = mapped_column(String(20), nullable=False)
    dcs: Mapped[int] = mapped_column(Integer, nullable=False)
    dcs_breakdown: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    location: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    occurrences: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    facts: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    inferred: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    evidence_ids: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    test_execution_ids: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    # Phase 5 defect intelligence (all derived from persisted results; never from model opinion).
    description: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    affected_tests: Mapped[dict[str, Any]] = mapped_column(
        default=dict, server_default="{}", nullable=False
    )
    reproducibility: Mapped[dict[str, Any]] = mapped_column(
        default=dict, server_default="{}", nullable=False
    )
    root_causes: Mapped[dict[str, Any]] = mapped_column(
        default=dict, server_default="{}", nullable=False
    )
    risk_priority: Mapped[float] = mapped_column(
        Numeric(5, 2), default=0, server_default="0", nullable=False
    )
    priority_breakdown: Mapped[dict[str, Any]] = mapped_column(
        default=dict, server_default="{}", nullable=False
    )
    history: Mapped[dict[str, Any]] = mapped_column(
        default=dict, server_default="{}", nullable=False
    )
    status_history: Mapped[dict[str, Any]] = mapped_column(
        default=dict, server_default="{}", nullable=False
    )
    triage: Mapped[dict[str, Any]] = mapped_column(
        default=dict, server_default="{}", nullable=False
    )
    duplicate_of: Mapped[str | None] = mapped_column(String(40))
    disputed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
