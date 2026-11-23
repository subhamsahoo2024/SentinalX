"""add policies table

Revision ID: 0002_add_policies_table
Revises: 4507264f02e6
Create Date: 2026-11-23 11:15:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_add_policies_table"
down_revision: str | Sequence[str] | None = "4507264f02e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "policies",
        sa.Column("policy_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("team", sa.String(), nullable=True),
        sa.Column("agent_id", sa.String(), nullable=True),
        sa.Column("max_tokens", sa.Integer(), server_default="5000", nullable=False),
        sa.Column(
            "max_cost_usd",
            sa.Numeric(precision=10, scale=4),
            server_default="0.5000",
            nullable=False,
        ),
        sa.Column("loop_threshold", sa.Integer(), server_default="3", nullable=False),
        sa.Column(
            "loop_window_sec", sa.Integer(), server_default="30", nullable=False
        ),
        sa.Column(
            "auto_block_on_budget",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        sa.Column(
            "protected_tools",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("policy_id"),
    )


def downgrade() -> None:
    op.drop_table("policies")
