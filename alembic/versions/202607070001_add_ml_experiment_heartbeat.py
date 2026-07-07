"""add ml experiment heartbeat

Revision ID: 202607070001
Revises: 202606240001
Create Date: 2026-07-07 00:01:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202607070001"
down_revision: Union[str, None] = "202606240001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("ml_experiments", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_ml_experiments_heartbeat_at"), "ml_experiments", ["heartbeat_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_ml_experiments_heartbeat_at"), table_name="ml_experiments")
    op.drop_column("ml_experiments", "heartbeat_at")
