"""phase 5 defect intelligence

Revision ID: 7c1e5d2a9b40
Revises: 4a32de149091
Create Date: 2026-10-24 09:00:00+00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "7c1e5d2a9b40"
down_revision = "4a32de149091"
branch_labels = None
depends_on = None

_JSON_COLUMNS = (
    "affected_tests",
    "reproducibility",
    "root_causes",
    "priority_breakdown",
    "history",
    "status_history",
    "triage",
)


def upgrade() -> None:
    op.add_column(
        "findings",
        sa.Column("description", sa.Text(), server_default="", nullable=False),
    )
    for name in _JSON_COLUMNS:
        op.add_column(
            "findings",
            sa.Column(
                name,
                postgresql.JSONB(astext_type=sa.Text()),
                server_default="{}",
                nullable=False,
            ),
        )
    op.add_column(
        "findings",
        sa.Column("risk_priority", sa.Numeric(5, 2), server_default="0", nullable=False),
    )
    op.add_column("findings", sa.Column("duplicate_of", sa.String(length=40), nullable=True))
    op.add_column(
        "findings",
        sa.Column("disputed", sa.Boolean(), server_default="false", nullable=False),
    )
    op.create_index(
        "ix_findings_org_risk_priority", "findings", ["org_id", "risk_priority"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_findings_org_risk_priority", table_name="findings")
    op.drop_column("findings", "disputed")
    op.drop_column("findings", "duplicate_of")
    op.drop_column("findings", "risk_priority")
    for name in reversed(_JSON_COLUMNS):
        op.drop_column("findings", name)
    op.drop_column("findings", "description")
