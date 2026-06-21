"""add microstructure dataset features

Revision ID: 202606210004
Revises: 202606210003
Create Date: 2026-06-21 00:04:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "202606210004"
down_revision: Union[str, None] = "202606210003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "market_recent_trades_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("exchange_credential_id", sa.Integer(), nullable=False),
        sa.Column("exchange_market_id", sa.Integer(), nullable=False),
        sa.Column("exchange_code", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=120), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trades_json", sa.JSON(), nullable=True),
        sa.Column("trades_count", sa.Integer(), nullable=False),
        sa.Column("buy_volume", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("sell_volume", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("buy_sell_delta", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("buy_sell_ratio", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("avg_trade_size", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("large_trade_count", sa.Integer(), nullable=True),
        sa.Column("largest_trade_size", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["exchange_credential_id"], ["exchange_credentials.id"]),
        sa.ForeignKeyConstraint(["exchange_market_id"], ["exchange_markets.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index(op.f("ix_market_recent_trades_snapshots_captured_at"), "market_recent_trades_snapshots", ["captured_at"], unique=False)
    op.create_index(op.f("ix_market_recent_trades_snapshots_id"), "market_recent_trades_snapshots", ["id"], unique=False)
    op.create_index(op.f("ix_market_recent_trades_snapshots_public_id"), "market_recent_trades_snapshots", ["public_id"], unique=True)

    op.create_table(
        "market_micro_candles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("exchange_credential_id", sa.Integer(), nullable=False),
        sa.Column("exchange_market_id", sa.Integer(), nullable=False),
        sa.Column("exchange_code", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=120), nullable=False),
        sa.Column("timeframe", sa.String(length=16), nullable=False),
        sa.Column("open", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("high", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("low", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("close", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("volume", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_ohlcv_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["exchange_credential_id"], ["exchange_credentials.id"]),
        sa.ForeignKeyConstraint(["exchange_market_id"], ["exchange_markets.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index(op.f("ix_market_micro_candles_id"), "market_micro_candles", ["id"], unique=False)
    op.create_index(op.f("ix_market_micro_candles_public_id"), "market_micro_candles", ["public_id"], unique=True)
    op.create_index(op.f("ix_market_micro_candles_timestamp"), "market_micro_candles", ["timestamp"], unique=False)

    columns = [
        ("buy_volume", sa.Numeric(precision=28, scale=12)),
        ("sell_volume", sa.Numeric(precision=28, scale=12)),
        ("buy_sell_delta", sa.Numeric(precision=28, scale=12)),
        ("buy_sell_ratio", sa.Numeric(precision=28, scale=12)),
        ("avg_trade_size", sa.Numeric(precision=28, scale=12)),
        ("large_trade_count", sa.Integer()),
        ("largest_trade_size", sa.Numeric(precision=28, scale=12)),
        ("bid_depth_5_delta", sa.Numeric(precision=28, scale=12)),
        ("ask_depth_5_delta", sa.Numeric(precision=28, scale=12)),
        ("imbalance_5_delta", sa.Numeric(precision=28, scale=12)),
        ("bid_depth_10_delta", sa.Numeric(precision=28, scale=12)),
        ("ask_depth_10_delta", sa.Numeric(precision=28, scale=12)),
        ("imbalance_10_delta", sa.Numeric(precision=28, scale=12)),
        ("spread_delta", sa.Numeric(precision=28, scale=12)),
        ("mid_price_delta", sa.Numeric(precision=28, scale=12)),
        ("wall_shift_score", sa.Numeric(precision=28, scale=12)),
        ("candle_return_1", sa.Numeric(precision=28, scale=12)),
        ("candle_return_3", sa.Numeric(precision=28, scale=12)),
        ("candle_volume_1", sa.Numeric(precision=28, scale=12)),
        ("candle_volume_avg_5", sa.Numeric(precision=28, scale=12)),
        ("candle_momentum_5", sa.Numeric(precision=28, scale=12)),
        ("funding_rate_delta", sa.Numeric(precision=28, scale=12)),
        ("funding_rate_abs", sa.Numeric(precision=28, scale=12)),
        ("funding_pressure_score", sa.Numeric(precision=28, scale=12)),
        ("capture_latency_ms", sa.Integer()),
        ("order_book_timestamp", sa.DateTime(timezone=True)),
        ("ticker_timestamp", sa.DateTime(timezone=True)),
        ("trades_timestamp", sa.DateTime(timezone=True)),
        ("data_quality_score", sa.Integer()),
        ("missing_fields_count", sa.Integer()),
    ]
    for name, column_type in columns:
        op.add_column("ml_feature_snapshots", sa.Column(name, column_type, nullable=True))


def downgrade() -> None:
    for name in [
        "missing_fields_count",
        "data_quality_score",
        "trades_timestamp",
        "ticker_timestamp",
        "order_book_timestamp",
        "capture_latency_ms",
        "funding_pressure_score",
        "funding_rate_abs",
        "funding_rate_delta",
        "candle_momentum_5",
        "candle_volume_avg_5",
        "candle_volume_1",
        "candle_return_3",
        "candle_return_1",
        "wall_shift_score",
        "mid_price_delta",
        "spread_delta",
        "imbalance_10_delta",
        "ask_depth_10_delta",
        "bid_depth_10_delta",
        "imbalance_5_delta",
        "ask_depth_5_delta",
        "bid_depth_5_delta",
        "largest_trade_size",
        "large_trade_count",
        "avg_trade_size",
        "buy_sell_ratio",
        "buy_sell_delta",
        "sell_volume",
        "buy_volume",
    ]:
        op.drop_column("ml_feature_snapshots", name)

    op.drop_index(op.f("ix_market_micro_candles_timestamp"), table_name="market_micro_candles")
    op.drop_index(op.f("ix_market_micro_candles_public_id"), table_name="market_micro_candles")
    op.drop_index(op.f("ix_market_micro_candles_id"), table_name="market_micro_candles")
    op.drop_table("market_micro_candles")
    op.drop_index(op.f("ix_market_recent_trades_snapshots_public_id"), table_name="market_recent_trades_snapshots")
    op.drop_index(op.f("ix_market_recent_trades_snapshots_id"), table_name="market_recent_trades_snapshots")
    op.drop_index(op.f("ix_market_recent_trades_snapshots_captured_at"), table_name="market_recent_trades_snapshots")
    op.drop_table("market_recent_trades_snapshots")
