"""add advanced ml label fields

Revision ID: 202606220001
Revises: 202606210004
Create Date: 2026-06-22 00:01:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202606220001"
down_revision: Union[str, None] = "202606210004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    columns = [
        ("long_mfe_percent", sa.Numeric(precision=28, scale=12)),
        ("long_mae_percent", sa.Numeric(precision=28, scale=12)),
        ("short_mfe_percent", sa.Numeric(precision=28, scale=12)),
        ("short_mae_percent", sa.Numeric(precision=28, scale=12)),
        ("long_tp_hit_0_2", sa.Boolean()),
        ("long_sl_hit_0_2", sa.Boolean()),
        ("short_tp_hit_0_2", sa.Boolean()),
        ("short_sl_hit_0_2", sa.Boolean()),
        ("long_tp_hit_0_3", sa.Boolean()),
        ("long_sl_hit_0_3", sa.Boolean()),
        ("short_tp_hit_0_3", sa.Boolean()),
        ("short_sl_hit_0_3", sa.Boolean()),
        ("long_tp_hit_0_5", sa.Boolean()),
        ("long_sl_hit_0_5", sa.Boolean()),
        ("short_tp_hit_0_5", sa.Boolean()),
        ("short_sl_hit_0_5", sa.Boolean()),
        ("long_tp_hit_1_0", sa.Boolean()),
        ("long_sl_hit_1_0", sa.Boolean()),
        ("short_tp_hit_1_0", sa.Boolean()),
        ("short_sl_hit_1_0", sa.Boolean()),
        ("best_long_tp_percent", sa.Numeric(precision=28, scale=12)),
        ("best_short_tp_percent", sa.Numeric(precision=28, scale=12)),
        ("best_long_sl_percent", sa.Numeric(precision=28, scale=12)),
        ("best_short_sl_percent", sa.Numeric(precision=28, scale=12)),
        ("expected_long_return_percent", sa.Numeric(precision=28, scale=12)),
        ("expected_short_return_percent", sa.Numeric(precision=28, scale=12)),
    ]
    for name, column_type in columns:
        op.add_column("ml_snapshot_labels", sa.Column(name, column_type, nullable=True))


def downgrade() -> None:
    for name in [
        "expected_short_return_percent",
        "expected_long_return_percent",
        "best_short_sl_percent",
        "best_long_sl_percent",
        "best_short_tp_percent",
        "best_long_tp_percent",
        "short_sl_hit_1_0",
        "short_tp_hit_1_0",
        "long_sl_hit_1_0",
        "long_tp_hit_1_0",
        "short_sl_hit_0_5",
        "short_tp_hit_0_5",
        "long_sl_hit_0_5",
        "long_tp_hit_0_5",
        "short_sl_hit_0_3",
        "short_tp_hit_0_3",
        "long_sl_hit_0_3",
        "long_tp_hit_0_3",
        "short_sl_hit_0_2",
        "short_tp_hit_0_2",
        "long_sl_hit_0_2",
        "long_tp_hit_0_2",
        "short_mae_percent",
        "short_mfe_percent",
        "long_mae_percent",
        "long_mfe_percent",
    ]:
        op.drop_column("ml_snapshot_labels", name)
