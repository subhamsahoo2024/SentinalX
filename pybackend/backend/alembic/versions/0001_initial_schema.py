"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-11-17 17:15:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. agents table
    op.create_table(
        "agents",
        sa.Column("agent_id", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("framework", sa.String(), nullable=False),
        sa.Column("team", sa.String(), nullable=False),
        sa.Column(
            "environment", sa.String(), server_default="development", nullable=False
        ),
        sa.Column(
            "declared_tools",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("agent_id"),
    )

    # 2. runs table
    op.create_table(
        "runs",
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("trace_id", sa.String(), nullable=False),
        sa.Column("root_agent_id", sa.String(), nullable=True),
        sa.Column("team", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_cost_usd", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column(
            "cost_status", sa.String(), server_default="UNKNOWN", nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["root_agent_id"], ["agents.agent_id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index(op.f("ix_runs_trace_id"), "runs", ["trace_id"], unique=True)

    # 3. spans table
    op.create_table(
        "spans",
        sa.Column("span_id", sa.String(), nullable=False),
        sa.Column("trace_id", sa.String(), nullable=False),
        sa.Column("parent_span_id", sa.String(), nullable=True),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("agent_id", sa.String(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), server_default="1", nullable=False),
        sa.Column("span_type", sa.String(), nullable=False),
        sa.Column("operation_name", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("model_provider", sa.String(), nullable=True),
        sa.Column("model_name", sa.String(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cached_tokens", sa.Integer(), nullable=True),
        sa.Column("direct_cost_usd", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column(
            "cost_basis", sa.String(), server_default="UNKNOWN", nullable=False
        ),
        sa.Column(
            "is_root_cause", sa.Boolean(), server_default="false", nullable=False
        ),
        sa.Column("error_class", sa.String(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["run_id"], ["runs.run_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("span_id"),
    )
    op.create_index(op.f("ix_spans_agent_id"), "spans", ["agent_id"], unique=False)
    op.create_index(
        op.f("ix_spans_parent_span_id"), "spans", ["parent_span_id"], unique=False
    )
    op.create_index(op.f("ix_spans_run_id"), "spans", ["run_id"], unique=False)
    op.create_index(op.f("ix_spans_trace_id"), "spans", ["trace_id"], unique=False)

    # 4. approvals table
    op.create_table(
        "approvals",
        sa.Column("approval_id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("span_id", sa.String(), nullable=False),
        sa.Column("agent_id", sa.String(), nullable=False),
        sa.Column("tool_name", sa.String(), nullable=False),
        sa.Column(
            "sanitized_args",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("risk_level", sa.String(), nullable=False),
        sa.Column("policy_reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), server_default="PENDING", nullable=False),
        sa.Column("decided_by", sa.String(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["runs.run_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["span_id"], ["spans.span_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("approval_id"),
        sa.UniqueConstraint("span_id"),
    )
    op.create_index(
        op.f("ix_approvals_run_id"), "approvals", ["run_id"], unique=False
    )

    # 5. alerts table
    op.create_table(
        "alerts",
        sa.Column("alert_id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("origin_span_id", sa.String(), nullable=True),
        sa.Column("rule_id", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column(
            "evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "impacted_span_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "acknowledged", sa.Boolean(), server_default="false", nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["runs.run_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("alert_id"),
    )
    op.create_index(op.f("ix_alerts_run_id"), "alerts", ["run_id"], unique=False)

    # 6. pricing_versions table
    op.create_table(
        "pricing_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("model_name", sa.String(), nullable=False),
        sa.Column("version_tag", sa.String(), nullable=False),
        sa.Column(
            "input_rate_per_1m", sa.Numeric(precision=10, scale=4), nullable=False
        ),
        sa.Column(
            "output_rate_per_1m", sa.Numeric(precision=10, scale=4), nullable=False
        ),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # 7. audit_events table
    op.create_table(
        "audit_events",
        sa.Column("audit_id", sa.String(), nullable=False),
        sa.Column("actor_id", sa.String(), nullable=False),
        sa.Column("actor_role", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("target_type", sa.String(), nullable=False),
        sa.Column("target_id", sa.String(), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("audit_id"),
    )

    # 8. PostgreSQL function & trigger enforcing strictly append-only audit_events
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_audit_events_modification()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'audit_events table is strictly append-only: % operations are prohibited', TG_OP;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_events_prevent_mutation
        BEFORE UPDATE OR DELETE ON audit_events
        FOR EACH ROW
        EXECUTE FUNCTION prevent_audit_events_modification();
        """
    )


def downgrade() -> None:
    # Remove trigger and function
    op.execute(
        "DROP TRIGGER IF EXISTS trg_audit_events_prevent_mutation ON audit_events;"
    )
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_events_modification();")

    # Drop tables in reverse creation order
    op.drop_table("audit_events")
    op.drop_table("pricing_versions")
    op.drop_index(op.f("ix_alerts_run_id"), table_name="alerts")
    op.drop_table("alerts")
    op.drop_index(op.f("ix_approvals_run_id"), table_name="approvals")
    op.drop_table("approvals")
    op.drop_index(op.f("ix_spans_trace_id"), table_name="spans")
    op.drop_index(op.f("ix_spans_run_id"), table_name="spans")
    op.drop_index(op.f("ix_spans_parent_span_id"), table_name="spans")
    op.drop_index(op.f("ix_spans_agent_id"), table_name="spans")
    op.drop_table("spans")
    op.drop_index(op.f("ix_runs_trace_id"), table_name="runs")
    op.drop_table("runs")
    op.drop_table("agents")

