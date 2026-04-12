"""add_world_schema_fields

Revision ID: 0002_add_world_schema_fields
Revises: 0001_initial_baseline
Create Date: 2026-04-11 00:05:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_add_world_schema_fields"
down_revision = "0001_initial_baseline"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def upgrade() -> None:
    if not _has_column("world_sandboxes", "runtime_world_json"):
        with op.batch_alter_table("world_sandboxes") as batch_op:
            batch_op.add_column(sa.Column("runtime_world_json", sa.Text(), nullable=True))

    if not _has_column("world_sandboxes", "user_id"):
        with op.batch_alter_table("world_sandboxes") as batch_op:
            batch_op.add_column(
                sa.Column("user_id", sa.String(length=100), nullable=False, server_default="local")
            )

    if not _has_column("story_concepts", "user_id"):
        with op.batch_alter_table("story_concepts") as batch_op:
            batch_op.add_column(
                sa.Column("user_id", sa.String(length=100), nullable=False, server_default="local")
            )


def downgrade() -> None:
    if _has_column("story_concepts", "user_id"):
        with op.batch_alter_table("story_concepts") as batch_op:
            batch_op.drop_column("user_id")

    if _has_column("world_sandboxes", "user_id"):
        with op.batch_alter_table("world_sandboxes") as batch_op:
            batch_op.drop_column("user_id")

    if _has_column("world_sandboxes", "runtime_world_json"):
        with op.batch_alter_table("world_sandboxes") as batch_op:
            batch_op.drop_column("runtime_world_json")