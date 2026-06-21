"""create exchange credentials

Revision ID: 202606210001
Revises: 
Create Date: 2026-06-21 00:01:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "202606210001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "exchange_credentials",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("exchange_code", sa.String(length=64), nullable=False),
        sa.Column("icon_path", sa.String(length=500), nullable=True),
        sa.Column("sort_index", sa.Integer(), nullable=False),
        sa.Column("api_key_encrypted", sa.Text(), nullable=False),
        sa.Column("api_secret_encrypted", sa.Text(), nullable=False),
        sa.Column("password_encrypted", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_futures_enabled", sa.Boolean(), nullable=False),
        sa.Column("last_test_status", sa.String(length=32), nullable=True),
        sa.Column("last_test_message", sa.Text(), nullable=True),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index(op.f("ix_exchange_credentials_exchange_code"), "exchange_credentials", ["exchange_code"], unique=False)
    op.create_index(op.f("ix_exchange_credentials_id"), "exchange_credentials", ["id"], unique=False)
    op.create_index(op.f("ix_exchange_credentials_public_id"), "exchange_credentials", ["public_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_exchange_credentials_public_id"), table_name="exchange_credentials")
    op.drop_index(op.f("ix_exchange_credentials_id"), table_name="exchange_credentials")
    op.drop_index(op.f("ix_exchange_credentials_exchange_code"), table_name="exchange_credentials")
    op.drop_table("exchange_credentials")
