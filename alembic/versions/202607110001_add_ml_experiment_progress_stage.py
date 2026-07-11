"""add ml experiment progress stage

Revision ID: 202607110001
Revises: 202607070001
Create Date: 2026-07-11 00:01:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202607110001"
down_revision: Union[str, None] = "202607070001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("ml_experiments", sa.Column("progress_stage", sa.String(length=80), nullable=True))
    op.create_index(op.f("ix_ml_experiments_progress_stage"), "ml_experiments", ["progress_stage"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_ml_experiments_progress_stage"), table_name="ml_experiments")
    op.drop_column("ml_experiments", "progress_stage")
