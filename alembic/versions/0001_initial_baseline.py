"""initial_baseline

Revision ID: 0001_initial_baseline
Revises: None
Create Date: 2026-04-11 00:00:00
"""

from __future__ import annotations

from alembic import op

from narrative_os.infra.database import Base
from narrative_os.infra import models as _models  # noqa: F401

revision = "0001_initial_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)