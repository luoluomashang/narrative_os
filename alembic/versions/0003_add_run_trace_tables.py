"""add_run_trace_tables

Revision ID: 0003_add_run_trace_tables
Revises: 0002_add_world_schema_fields
Create Date: 2026-04-12 09:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003_add_run_trace_tables"
down_revision = "0002_add_world_schema_fields"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return inspector.has_table(table_name)


def upgrade() -> None:
    if not _has_table("runs"):
        op.create_table(
            "runs",
            sa.Column("id", sa.String(length=100), primary_key=True),
            sa.Column("project_id", sa.String(length=100), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
            sa.Column("run_type", sa.String(length=50), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False, server_default="running"),
            sa.Column("chapter_num", sa.Integer(), nullable=True),
            sa.Column("session_id", sa.String(length=100), nullable=True),
            sa.Column("total_cost_usd", sa.Float(), nullable=False, server_default="0"),
            sa.Column("user_id", sa.String(length=100), nullable=False, server_default="local"),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("ended_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_runs_project_id", "runs", ["project_id"])

    if not _has_table("run_steps"):
        op.create_table(
            "run_steps",
            sa.Column("id", sa.String(length=100), primary_key=True),
            sa.Column("run_id", sa.String(length=100), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("step_index", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("agent_name", sa.String(length=100), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=30), nullable=False, server_default="running"),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("ended_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_run_steps_run_id", "run_steps", ["run_id"])
        op.create_index("ix_run_steps_run_step", "run_steps", ["run_id", "step_index"])

    if not _has_table("artifacts"):
        op.create_table(
            "artifacts",
            sa.Column("id", sa.String(length=100), primary_key=True),
            sa.Column("run_id", sa.String(length=100), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("step_id", sa.String(length=100), sa.ForeignKey("run_steps.id", ondelete="CASCADE"), nullable=False),
            sa.Column("artifact_type", sa.String(length=50), nullable=False, server_default="draft"),
            sa.Column("agent_name", sa.String(length=100), nullable=False, server_default=""),
            sa.Column("input_summary", sa.Text(), nullable=False, server_default=""),
            sa.Column("output_content", sa.Text(), nullable=False, server_default=""),
            sa.Column("quality_scores", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("token_in", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("token_out", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("retry_reason", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_artifacts_run_id", "artifacts", ["run_id"])
        op.create_index("ix_artifacts_step_id", "artifacts", ["step_id"])

    if not _has_table("approval_checkpoints"):
        op.create_table(
            "approval_checkpoints",
            sa.Column("id", sa.String(length=100), primary_key=True),
            sa.Column("run_id", sa.String(length=100), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False, server_default=""),
            sa.Column("context", sa.Text(), nullable=False, server_default=""),
            sa.Column("decision", sa.String(length=30), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("resolved_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_approval_checkpoints_run_id", "approval_checkpoints", ["run_id"])


def downgrade() -> None:
    if _has_table("approval_checkpoints"):
        op.drop_index("ix_approval_checkpoints_run_id", table_name="approval_checkpoints")
        op.drop_table("approval_checkpoints")

    if _has_table("artifacts"):
        op.drop_index("ix_artifacts_step_id", table_name="artifacts")
        op.drop_index("ix_artifacts_run_id", table_name="artifacts")
        op.drop_table("artifacts")

    if _has_table("run_steps"):
        op.drop_index("ix_run_steps_run_step", table_name="run_steps")
        op.drop_index("ix_run_steps_run_id", table_name="run_steps")
        op.drop_table("run_steps")

    if _has_table("runs"):
        op.drop_index("ix_runs_project_id", table_name="runs")
        op.drop_table("runs")