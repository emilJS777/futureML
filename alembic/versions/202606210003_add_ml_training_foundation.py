"""add ml training foundation

Revision ID: 202606210003
Revises: 202606210002
Create Date: 2026-06-21 00:03:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "202606210003"
down_revision: Union[str, None] = "202606210002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ml_training_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("interval_seconds", sa.Integer(), nullable=False),
        sa.Column("label_horizons_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index(op.f("ix_ml_training_sessions_id"), "ml_training_sessions", ["id"], unique=False)
    op.create_index(op.f("ix_ml_training_sessions_public_id"), "ml_training_sessions", ["public_id"], unique=True)
    op.create_index(op.f("ix_ml_training_sessions_status"), "ml_training_sessions", ["status"], unique=False)

    op.create_table(
        "ml_feature_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("training_session_id", sa.Integer(), nullable=True),
        sa.Column("exchange_credential_id", sa.Integer(), nullable=False),
        sa.Column("exchange_market_id", sa.Integer(), nullable=False),
        sa.Column("exchange_code", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=120), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("best_bid", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("best_ask", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("spread", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("spread_percent", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("mid_price", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("last_price", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("mark_price", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("index_price", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("funding_rate", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("open_interest", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("volume_24h", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("quote_volume_24h", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("price_change_percent_24h", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("bid_depth_5", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("ask_depth_5", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("bid_depth_10", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("ask_depth_10", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("bid_depth_20", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("ask_depth_20", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("order_book_imbalance_5", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("order_book_imbalance_10", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("order_book_imbalance_20", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("top_bid_size", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("top_ask_size", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("bid_wall_score", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("ask_wall_score", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("cross_exchange_mid_avg", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("cross_exchange_mid_median", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("cross_exchange_price_deviation_percent", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("cross_exchange_spread_percent", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("raw_snapshot_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["exchange_credential_id"], ["exchange_credentials.id"]),
        sa.ForeignKeyConstraint(["exchange_market_id"], ["exchange_markets.id"]),
        sa.ForeignKeyConstraint(["training_session_id"], ["ml_training_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index(op.f("ix_ml_feature_snapshots_captured_at"), "ml_feature_snapshots", ["captured_at"], unique=False)
    op.create_index(op.f("ix_ml_feature_snapshots_exchange_code"), "ml_feature_snapshots", ["exchange_code"], unique=False)
    op.create_index(op.f("ix_ml_feature_snapshots_id"), "ml_feature_snapshots", ["id"], unique=False)
    op.create_index(op.f("ix_ml_feature_snapshots_public_id"), "ml_feature_snapshots", ["public_id"], unique=True)
    op.create_index(op.f("ix_ml_feature_snapshots_symbol"), "ml_feature_snapshots", ["symbol"], unique=False)

    op.create_table(
        "ml_snapshot_labels",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("feature_snapshot_id", sa.Integer(), nullable=False),
        sa.Column("horizon_seconds", sa.Integer(), nullable=False),
        sa.Column("future_mid_price", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("future_return_percent", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("direction_label", sa.String(length=16), nullable=True),
        sa.Column("long_would_win", sa.Boolean(), nullable=True),
        sa.Column("short_would_win", sa.Boolean(), nullable=True),
        sa.Column("is_labeled", sa.Boolean(), nullable=False),
        sa.Column("labeled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["feature_snapshot_id"], ["ml_feature_snapshots.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index(op.f("ix_ml_snapshot_labels_horizon_seconds"), "ml_snapshot_labels", ["horizon_seconds"], unique=False)
    op.create_index(op.f("ix_ml_snapshot_labels_id"), "ml_snapshot_labels", ["id"], unique=False)
    op.create_index(op.f("ix_ml_snapshot_labels_is_labeled"), "ml_snapshot_labels", ["is_labeled"], unique=False)
    op.create_index(op.f("ix_ml_snapshot_labels_public_id"), "ml_snapshot_labels", ["public_id"], unique=True)

    op.create_table(
        "ml_models",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("model_type", sa.String(length=80), nullable=False),
        sa.Column("target_horizon_seconds", sa.Integer(), nullable=False),
        sa.Column("train_rows_count", sa.Integer(), nullable=False),
        sa.Column("accuracy", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("precision_long", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("precision_short", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("precision_flat", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("model_path", sa.String(length=500), nullable=True),
        sa.Column("feature_columns_json", sa.JSON(), nullable=False),
        sa.Column("metrics_json", sa.JSON(), nullable=True),
        sa.Column("trained_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index(op.f("ix_ml_models_id"), "ml_models", ["id"], unique=False)
    op.create_index(op.f("ix_ml_models_public_id"), "ml_models", ["public_id"], unique=True)
    op.create_index(op.f("ix_ml_models_trained_at"), "ml_models", ["trained_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_ml_models_trained_at"), table_name="ml_models")
    op.drop_index(op.f("ix_ml_models_public_id"), table_name="ml_models")
    op.drop_index(op.f("ix_ml_models_id"), table_name="ml_models")
    op.drop_table("ml_models")
    op.drop_index(op.f("ix_ml_snapshot_labels_public_id"), table_name="ml_snapshot_labels")
    op.drop_index(op.f("ix_ml_snapshot_labels_is_labeled"), table_name="ml_snapshot_labels")
    op.drop_index(op.f("ix_ml_snapshot_labels_id"), table_name="ml_snapshot_labels")
    op.drop_index(op.f("ix_ml_snapshot_labels_horizon_seconds"), table_name="ml_snapshot_labels")
    op.drop_table("ml_snapshot_labels")
    op.drop_index(op.f("ix_ml_feature_snapshots_symbol"), table_name="ml_feature_snapshots")
    op.drop_index(op.f("ix_ml_feature_snapshots_public_id"), table_name="ml_feature_snapshots")
    op.drop_index(op.f("ix_ml_feature_snapshots_id"), table_name="ml_feature_snapshots")
    op.drop_index(op.f("ix_ml_feature_snapshots_exchange_code"), table_name="ml_feature_snapshots")
    op.drop_index(op.f("ix_ml_feature_snapshots_captured_at"), table_name="ml_feature_snapshots")
    op.drop_table("ml_feature_snapshots")
    op.drop_index(op.f("ix_ml_training_sessions_status"), table_name="ml_training_sessions")
    op.drop_index(op.f("ix_ml_training_sessions_public_id"), table_name="ml_training_sessions")
    op.drop_index(op.f("ix_ml_training_sessions_id"), table_name="ml_training_sessions")
    op.drop_table("ml_training_sessions")
