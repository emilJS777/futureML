"""add ml experiments

Revision ID: 202606240001
Revises: 202606220001
Create Date: 2026-06-24 00:01:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "202606240001"
down_revision: Union[str, None] = "202606220001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ml_experiments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("model_type", sa.String(length=80), nullable=False),
        sa.Column("target_type", sa.String(length=80), nullable=False),
        sa.Column("horizon_seconds", sa.Integer(), nullable=False),
        sa.Column("confidence_threshold", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("min_rows", sa.Integer(), nullable=False),
        sa.Column("train_rows_count", sa.Integer(), nullable=True),
        sa.Column("test_rows_count", sa.Integer(), nullable=True),
        sa.Column("accuracy", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("precision_long", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("precision_short", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("precision_flat", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("recall_long", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("recall_short", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("recall_flat", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("f1_long", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("f1_short", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("f1_flat", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("confusion_matrix_json", sa.JSON(), nullable=True),
        sa.Column("feature_importance_json", sa.JSON(), nullable=True),
        sa.Column("classification_report_json", sa.JSON(), nullable=True),
        sa.Column("model_path", sa.String(length=500), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index(op.f("ix_ml_experiments_horizon_seconds"), "ml_experiments", ["horizon_seconds"], unique=False)
    op.create_index(op.f("ix_ml_experiments_id"), "ml_experiments", ["id"], unique=False)
    op.create_index(op.f("ix_ml_experiments_public_id"), "ml_experiments", ["public_id"], unique=True)
    op.create_index(op.f("ix_ml_experiments_status"), "ml_experiments", ["status"], unique=False)

    op.create_table(
        "ml_shadow_backtests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ml_experiment_id", sa.Integer(), nullable=False),
        sa.Column("horizon_seconds", sa.Integer(), nullable=False),
        sa.Column("confidence_threshold", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("total_signals", sa.Integer(), nullable=False),
        sa.Column("long_signals", sa.Integer(), nullable=False),
        sa.Column("short_signals", sa.Integer(), nullable=False),
        sa.Column("flat_skipped", sa.Integer(), nullable=False),
        sa.Column("win_count", sa.Integer(), nullable=False),
        sa.Column("loss_count", sa.Integer(), nullable=False),
        sa.Column("win_rate", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("avg_win_percent", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("avg_loss_percent", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("gross_profit_percent", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("gross_loss_percent", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("expectancy_percent", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("max_drawdown_percent", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("profit_factor", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("fees_percent", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("slippage_percent", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("net_expectancy_percent", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("equity_curve_json", sa.JSON(), nullable=True),
        sa.Column("results_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["ml_experiment_id"], ["ml_experiments.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index(
        op.f("ix_ml_shadow_backtests_ml_experiment_id"),
        "ml_shadow_backtests",
        ["ml_experiment_id"],
        unique=False,
    )
    op.create_index(op.f("ix_ml_shadow_backtests_id"), "ml_shadow_backtests", ["id"], unique=False)
    op.create_index(op.f("ix_ml_shadow_backtests_public_id"), "ml_shadow_backtests", ["public_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_ml_shadow_backtests_public_id"), table_name="ml_shadow_backtests")
    op.drop_index(op.f("ix_ml_shadow_backtests_id"), table_name="ml_shadow_backtests")
    op.drop_index(op.f("ix_ml_shadow_backtests_ml_experiment_id"), table_name="ml_shadow_backtests")
    op.drop_table("ml_shadow_backtests")
    op.drop_index(op.f("ix_ml_experiments_status"), table_name="ml_experiments")
    op.drop_index(op.f("ix_ml_experiments_public_id"), table_name="ml_experiments")
    op.drop_index(op.f("ix_ml_experiments_id"), table_name="ml_experiments")
    op.drop_index(op.f("ix_ml_experiments_horizon_seconds"), table_name="ml_experiments")
    op.drop_table("ml_experiments")
