"""phase 2: execution engine (worker runs, check runs, test executions, evidence, reports)

Revision ID: c2e1f7a90d44
Revises: b50874965b43
Create Date: 2026-10-24 12:00:00+00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c2e1f7a90d44"
down_revision = "b50874965b43"
branch_labels = None
depends_on = None


def _ts(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade() -> None:
    op.add_column("jobs", sa.Column("snapshot_sha256", sa.String(length=64), nullable=True))
    op.add_column(
        "jobs",
        sa.Column(
            "warnings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    op.create_table(
        "worker_runs",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("org_id", sa.String(length=40), nullable=False),
        sa.Column("job_id", sa.String(length=40), nullable=False),
        sa.Column("task_id", sa.String(length=40), nullable=False),
        sa.Column("attempt_id", sa.String(length=40), nullable=True),
        sa.Column("worker_id", sa.String(length=200), nullable=False),
        sa.Column("runtime", sa.String(length=40), nullable=False),
        sa.Column("isolation", sa.String(length=20), nullable=False),
        sa.Column("image_digest", sa.String(length=100), nullable=False),
        sa.Column("limits", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("network_policy", sa.String(length=40), nullable=False),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.String(length=30), nullable=True),
        sa.Column("output_bytes", sa.Integer(), nullable=False),
        sa.Column("truncated", sa.Boolean(), nullable=False),
        _ts("started_at"),
        _ts("ended_at", True),
        _ts("destroyed_at", True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint("id ~ '^wrk_'", name="ck_worker_runs_id_prefix"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_worker_runs_job_id", "worker_runs", ["job_id"])
    op.create_index("ix_worker_runs_org_id", "worker_runs", ["org_id"])
    op.create_index("ix_worker_runs_task_id", "worker_runs", ["task_id"])

    op.create_table(
        "check_runs",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("org_id", sa.String(length=40), nullable=False),
        sa.Column("job_id", sa.String(length=40), nullable=False),
        sa.Column("task_id", sa.String(length=40), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("worker_run_id", sa.String(length=40), nullable=True),
        sa.Column("engine_id", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        _ts("started_at"),
        _ts("ended_at"),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("tool_name", sa.String(length=80), nullable=False),
        sa.Column("tool_version", sa.String(length=80), nullable=False),
        sa.Column("executes_repository_code", sa.Boolean(), nullable=False),
        sa.Column("log_evidence_id", sa.String(length=40), nullable=True),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint("id ~ '^chk_'", name="ck_check_runs_id_prefix"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_check_runs_job_id", "check_runs", ["job_id"])
    op.create_index("ix_check_runs_org_id", "check_runs", ["org_id"])
    op.create_index("ix_check_runs_task_id", "check_runs", ["task_id"])
    op.create_index("ix_check_runs_job_engine", "check_runs", ["job_id", "engine_id"])

    op.create_table(
        "test_executions",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("org_id", sa.String(length=40), nullable=False),
        sa.Column("job_id", sa.String(length=40), nullable=False),
        sa.Column("task_id", sa.String(length=40), nullable=False),
        sa.Column("check_run_id", sa.String(length=40), nullable=False),
        sa.Column("worker_run_id", sa.String(length=40), nullable=True),
        sa.Column("node_id", sa.String(length=500), nullable=False),
        sa.Column("file", sa.String(length=500), nullable=True),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("purpose", sa.String(length=20), nullable=False),
        sa.Column("provenance", sa.String(length=20), nullable=False),
        sa.Column("tool_version", sa.String(length=80), nullable=False),
        sa.Column("commit_sha", sa.String(length=40), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint("id ~ '^tex_'", name="ck_test_executions_id_prefix"),
        sa.ForeignKeyConstraint(["check_run_id"], ["check_runs.id"]),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_test_executions_job_id", "test_executions", ["job_id"])
    op.create_index("ix_test_executions_org_id", "test_executions", ["org_id"])
    op.create_index("ix_test_executions_job_status", "test_executions", ["job_id", "status"])

    op.create_table(
        "evidence_items",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("org_id", sa.String(length=40), nullable=False),
        sa.Column("job_id", sa.String(length=40), nullable=False),
        sa.Column("task_id", sa.String(length=40), nullable=True),
        sa.Column("worker_run_id", sa.String(length=40), nullable=True),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=300), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("media_type", sa.String(length=80), nullable=False),
        sa.Column("producer", sa.String(length=120), nullable=False),
        sa.Column("redactions", sa.Integer(), nullable=False),
        sa.Column("truncated", sa.Boolean(), nullable=False),
        sa.Column("original_bytes", sa.Integer(), nullable=True),
        sa.Column("deterministic", sa.Boolean(), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint("id ~ '^evd_'", name="ck_evidence_items_id_prefix"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evidence_items_job_id", "evidence_items", ["job_id"])
    op.create_index("ix_evidence_items_org_id", "evidence_items", ["org_id"])
    op.create_index("ix_evidence_items_task_id", "evidence_items", ["task_id"])
    op.create_index("ix_evidence_items_sha", "evidence_items", ["org_id", "sha256"])

    op.create_table(
        "reports",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("org_id", sa.String(length=40), nullable=False),
        sa.Column("job_id", sa.String(length=40), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("verdict", sa.String(length=30), nullable=True),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("digest", sa.String(length=64), nullable=False),
        sa.Column("partial", sa.Boolean(), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint("id ~ '^rpt_'", name="ck_reports_id_prefix"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "kind", name="uq_reports_job_kind"),
    )
    op.create_index("ix_reports_job_id", "reports", ["job_id"])
    op.create_index("ix_reports_org_id", "reports", ["org_id"])


def downgrade() -> None:
    for table in ("reports", "evidence_items", "test_executions", "check_runs", "worker_runs"):
        op.drop_table(table)
    op.drop_column("jobs", "warnings")
    op.drop_column("jobs", "snapshot_sha256")
