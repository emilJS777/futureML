"""add exchange markets and market data snapshots

Revision ID: 202606210002
Revises: 202606210001
Create Date: 2026-06-21 00:02:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "202606210002"
down_revision: Union[str, None] = "202606210001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "exchange_markets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("exchange_credential_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=120), nullable=False),
        sa.Column("base", sa.String(length=64), nullable=True),
        sa.Column("quote", sa.String(length=64), nullable=True),
        sa.Column("settle", sa.String(length=64), nullable=True),
        sa.Column("market_type", sa.String(length=64), nullable=True),
        sa.Column("is_swap", sa.Boolean(), nullable=False),
        sa.Column("is_future", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_selected_for_data_collection", sa.Boolean(), nullable=False),
        sa.Column("raw_market_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["exchange_credential_id"], ["exchange_credentials.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("exchange_credential_id", "symbol", name="uq_exchange_markets_credential_symbol"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index(op.f("ix_exchange_markets_exchange_credential_id"), "exchange_markets", ["exchange_credential_id"], unique=False)
    op.create_index(op.f("ix_exchange_markets_id"), "exchange_markets", ["id"], unique=False)
    op.create_index(op.f("ix_exchange_markets_is_active"), "exchange_markets", ["is_active"], unique=False)
    op.create_index(op.f("ix_exchange_markets_public_id"), "exchange_markets", ["public_id"], unique=True)
    op.create_index(op.f("ix_exchange_markets_symbol"), "exchange_markets", ["symbol"], unique=False)

    op.create_table(
        "market_data_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("exchange_credential_id", sa.Integer(), nullable=False),
        sa.Column("exchange_market_id", sa.Integer(), nullable=True),
        sa.Column("exchange_code", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=120), nullable=False),
        sa.Column("best_bid", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("best_ask", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("spread", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("spread_percent", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("mid_price", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("last_price", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("mark_price", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("index_price", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("funding_rate", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("next_funding_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("open_interest", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("volume_24h", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("quote_volume_24h", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("price_change_percent_24h", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("order_book_bids_json", sa.JSON(), nullable=True),
        sa.Column("order_book_asks_json", sa.JSON(), nullable=True),
        sa.Column("order_book_depth", sa.Integer(), nullable=False),
        sa.Column("raw_ticker_json", sa.JSON(), nullable=True),
        sa.Column("raw_funding_json", sa.JSON(), nullable=True),
        sa.Column("raw_open_interest_json", sa.JSON(), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["exchange_credential_id"], ["exchange_credentials.id"]),
        sa.ForeignKeyConstraint(["exchange_market_id"], ["exchange_markets.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index(op.f("ix_market_data_snapshots_captured_at"), "market_data_snapshots", ["captured_at"], unique=False)
    op.create_index(op.f("ix_market_data_snapshots_exchange_code"), "market_data_snapshots", ["exchange_code"], unique=False)
    op.create_index(op.f("ix_market_data_snapshots_id"), "market_data_snapshots", ["id"], unique=False)
    op.create_index(op.f("ix_market_data_snapshots_public_id"), "market_data_snapshots", ["public_id"], unique=True)
    op.create_index(op.f("ix_market_data_snapshots_symbol"), "market_data_snapshots", ["symbol"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_market_data_snapshots_symbol"), table_name="market_data_snapshots")
    op.drop_index(op.f("ix_market_data_snapshots_public_id"), table_name="market_data_snapshots")
    op.drop_index(op.f("ix_market_data_snapshots_id"), table_name="market_data_snapshots")
    op.drop_index(op.f("ix_market_data_snapshots_exchange_code"), table_name="market_data_snapshots")
    op.drop_index(op.f("ix_market_data_snapshots_captured_at"), table_name="market_data_snapshots")
    op.drop_table("market_data_snapshots")
    op.drop_index(op.f("ix_exchange_markets_symbol"), table_name="exchange_markets")
    op.drop_index(op.f("ix_exchange_markets_public_id"), table_name="exchange_markets")
    op.drop_index(op.f("ix_exchange_markets_is_active"), table_name="exchange_markets")
    op.drop_index(op.f("ix_exchange_markets_id"), table_name="exchange_markets")
    op.drop_index(op.f("ix_exchange_markets_exchange_credential_id"), table_name="exchange_markets")
    op.drop_table("exchange_markets")
