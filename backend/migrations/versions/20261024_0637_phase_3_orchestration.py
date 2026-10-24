"""phase 3 orchestration (on top of the phase 2 execution engine)

Adds the agent-orchestration tables (approvals, job plans, agent outputs, findings), the job
inputs, and the agent-specific columns on the phase 2 evidence / test execution / report tables.

Revision ID: 4a32de149091
Revises: c2e1f7a90d44
Create Date: 2026-10-24 06:37:42.006350+00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "4a32de149091"
down_revision = "c2e1f7a90d44"
branch_labels = None
depends_on = None


def _jsonb() -> postgresql.JSONB:
    return postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    # --- jobs: supplied inputs and the HA-05 flag (warnings/snapshot come from phase 2)
    op.add_column("jobs", sa.Column("inputs", _jsonb(), server_default="{}", nullable=False))
    op.add_column(
        "jobs",
        sa.Column("require_plan_approval", sa.Boolean(), server_default="false", nullable=False),
    )

    # --- phase 2 tables gain the agent columns
    op.add_column("test_executions", sa.Column("scenario_id", sa.String(length=80)))
    op.add_column(
        "test_executions",
        sa.Column("test_type", sa.String(length=30), server_default="functional", nullable=False),
    )
    op.add_column(
        "test_executions", sa.Column("meta", _jsonb(), server_default="{}", nullable=False)
    )
    op.add_column(
        "test_executions",
        sa.Column("tool", sa.String(length=80), server_default="", nullable=False),
    )
    op.add_column("test_executions", sa.Column("evidence_id", sa.String(length=40)))
    op.alter_column("test_executions", "check_run_id", existing_type=sa.String(40), nullable=True)
    op.alter_column("test_executions", "node_id", existing_type=sa.String(500), server_default="")
    op.add_column("evidence_items", sa.Column("content", _jsonb(), nullable=True))
    op.add_column(
        "evidence_items",
        sa.Column(
            "redaction_status", sa.String(length=20), server_default="redacted", nullable=False
        ),
    )
    op.alter_column("evidence_items", "storage_key", existing_type=sa.String(300), nullable=True)
    op.add_column(
        "reports",
        sa.Column("generator", sa.String(length=80), server_default="", nullable=False),
    )

    # --- approvals
    op.create_table(
        "approvals",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("org_id", sa.String(length=40), nullable=False),
        sa.Column("ha_id", sa.String(length=10), nullable=False),
        sa.Column("subject_type", sa.String(length=40), nullable=False),
        sa.Column("subject_id", sa.String(length=40), nullable=False),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("approver_id", sa.String(length=200), nullable=False),
        sa.Column("role_at_decision", sa.String(length=40), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("subject_hash", sa.String(length=64), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id ~ '^apr_'", name="ck_approvals_id_prefix"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_approvals_org_id"), "approvals", ["org_id"], unique=False)
    op.create_index(op.f("ix_approvals_subject_id"), "approvals", ["subject_id"], unique=False)

    # --- job plans
    op.create_table(
        "job_plans",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("org_id", sa.String(length=40), nullable=False),
        sa.Column("job_id", sa.String(length=40), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.String(length=10), nullable=False),
        sa.Column("dag", _jsonb(), nullable=False),
        sa.Column("plan_hash", sa.String(length=64), nullable=False),
        sa.Column("approval_required", sa.Boolean(), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("planner", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id ~ '^pln_'", name="ck_job_plans_id_prefix"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "revision", name="uq_job_plans_job_revision"),
    )
    op.create_index(op.f("ix_job_plans_job_id"), "job_plans", ["job_id"], unique=False)
    op.create_index(op.f("ix_job_plans_org_id"), "job_plans", ["org_id"], unique=False)

    # --- agent outputs
    op.create_table(
        "agent_outputs",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("org_id", sa.String(length=40), nullable=False),
        sa.Column("job_id", sa.String(length=40), nullable=False),
        sa.Column("task_id", sa.String(length=40), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("agent_id", sa.String(length=10), nullable=False),
        sa.Column("agent_kind", sa.String(length=30), nullable=False),
        sa.Column("adapter", sa.String(length=60), nullable=False),
        sa.Column("model_ref", sa.String(length=120), nullable=True),
        sa.Column("schema_name", sa.String(length=60), nullable=False),
        sa.Column("schema_version", sa.String(length=10), nullable=False),
        sa.Column("validation_status", sa.String(length=20), nullable=False),
        sa.Column("input_sha256", sa.String(length=64), nullable=False),
        sa.Column("output_sha256", sa.String(length=64), nullable=False),
        sa.Column("payload", _jsonb(), nullable=False),
        sa.Column("tokens_in", sa.Integer(), nullable=False),
        sa.Column("tokens_out", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id ~ '^aout_'", name="ck_agent_outputs_id_prefix"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_outputs_job_id"), "agent_outputs", ["job_id"], unique=False)
    op.create_index(op.f("ix_agent_outputs_org_id"), "agent_outputs", ["org_id"], unique=False)
    op.create_index(op.f("ix_agent_outputs_task_id"), "agent_outputs", ["task_id"], unique=False)

    # --- findings
    op.create_table(
        "findings",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("org_id", sa.String(length=40), nullable=False),
        sa.Column("job_id", sa.String(length=40), nullable=False),
        sa.Column("display_id", sa.String(length=20), nullable=False),
        sa.Column("category", sa.String(length=60), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("confidence", sa.String(length=20), nullable=False),
        sa.Column("dcs", sa.Integer(), nullable=False),
        sa.Column("dcs_breakdown", _jsonb(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("location", _jsonb(), nullable=False),
        sa.Column("occurrences", sa.Integer(), nullable=False),
        sa.Column("facts", _jsonb(), nullable=False),
        sa.Column("inferred", _jsonb(), nullable=False),
        sa.Column("evidence_ids", _jsonb(), nullable=False),
        sa.Column("test_execution_ids", _jsonb(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id ~ '^fnd_'", name="ck_findings_id_prefix"),
        sa.CheckConstraint("dcs >= 0 AND dcs <= 100", name="ck_findings_dcs_range"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "display_id", name="uq_findings_org_display_id"),
    )
    op.create_index(op.f("ix_findings_job_id"), "findings", ["job_id"], unique=False)
    op.create_index(
        "ix_findings_org_fingerprint", "findings", ["org_id", "fingerprint"], unique=False
    )
    op.create_index(op.f("ix_findings_org_id"), "findings", ["org_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_findings_org_id"), table_name="findings")
    op.drop_index("ix_findings_org_fingerprint", table_name="findings")
    op.drop_index(op.f("ix_findings_job_id"), table_name="findings")
    op.drop_table("findings")
    op.drop_index(op.f("ix_agent_outputs_task_id"), table_name="agent_outputs")
    op.drop_index(op.f("ix_agent_outputs_org_id"), table_name="agent_outputs")
    op.drop_index(op.f("ix_agent_outputs_job_id"), table_name="agent_outputs")
    op.drop_table("agent_outputs")
    op.drop_index(op.f("ix_job_plans_org_id"), table_name="job_plans")
    op.drop_index(op.f("ix_job_plans_job_id"), table_name="job_plans")
    op.drop_table("job_plans")
    op.drop_index(op.f("ix_approvals_subject_id"), table_name="approvals")
    op.drop_index(op.f("ix_approvals_org_id"), table_name="approvals")
    op.drop_table("approvals")
    op.drop_column("reports", "generator")
    op.alter_column("evidence_items", "storage_key", existing_type=sa.String(300), nullable=False)
    op.drop_column("evidence_items", "redaction_status")
    op.drop_column("evidence_items", "content")
    op.alter_column("test_executions", "check_run_id", existing_type=sa.String(40), nullable=False)
    op.drop_column("test_executions", "evidence_id")
    op.drop_column("test_executions", "tool")
    op.drop_column("test_executions", "meta")
    op.drop_column("test_executions", "test_type")
    op.drop_column("test_executions", "scenario_id")
    op.drop_column("jobs", "require_plan_approval")
    op.drop_column("jobs", "inputs")
