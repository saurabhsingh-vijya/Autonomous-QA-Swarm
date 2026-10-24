"""phase 4: target environments, authorizations (HA-01) and job inputs

Revision ID: d4a7c3e1b905
Revises: c2e1f7a90d44
Create Date: 2026-10-24 18:00:00+00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "d4a7c3e1b905"
down_revision = "c2e1f7a90d44"
branch_labels = None
depends_on = None


def _ts(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column(
            "inputs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_table(
        "target_environments",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("org_id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("environment_type", sa.String(length=30), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("owner", sa.String(length=200), nullable=False),
        sa.Column("network_scope", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("credential_ref_id", sa.String(length=40), nullable=True),
        _ts("archived_at", True),
        sa.Column("version", sa.Integer(), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint("id ~ '^tgt_'", name="ck_target_environments_id_prefix"),
        sa.CheckConstraint(
            "kind IN ('registered', 'ephemeral')", name="ck_target_environments_kind"
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "project_id", "name", name="uq_targets_project_name"),
    )
    op.create_index("ix_target_environments_org_id", "target_environments", ["org_id"])
    op.create_index("ix_target_environments_project_id", "target_environments", ["project_id"])
    op.create_table(
        "target_authorizations",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("org_id", sa.String(length=40), nullable=False),
        sa.Column("target_id", sa.String(length=40), nullable=False),
        sa.Column("attested_by", sa.String(length=200), nullable=False),
        sa.Column("attested_role", sa.String(length=40), nullable=False),
        sa.Column("allowed_activities", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        _ts("valid_from"),
        _ts("valid_until"),
        _ts("revoked_at", True),
        sa.Column("note", sa.Text(), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint("id ~ '^tauth_'", name="ck_target_authorizations_id_prefix"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["target_id"], ["target_environments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_target_authorizations_org_id", "target_authorizations", ["org_id"])
    op.create_index("ix_target_authorizations_target_id", "target_authorizations", ["target_id"])
    op.create_index(
        "ix_target_authorizations_target", "target_authorizations", ["target_id", "valid_until"]
    )


def downgrade() -> None:
    op.drop_table("target_authorizations")
    op.drop_table("target_environments")
    op.drop_column("jobs", "inputs")
