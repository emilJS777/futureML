import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ExchangeMarket(Base):
    __tablename__ = "exchange_markets"
    __table_args__ = (
        UniqueConstraint("exchange_credential_id", "symbol", name="uq_exchange_markets_credential_symbol"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, index=True, nullable=False, default=uuid.uuid4
    )
    exchange_credential_id: Mapped[int] = mapped_column(ForeignKey("exchange_credentials.id"), nullable=False)
    symbol: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    base: Mapped[str | None] = mapped_column(String(64), nullable=True)
    quote: Mapped[str | None] = mapped_column(String(64), nullable=True)
    settle: Mapped[str | None] = mapped_column(String(64), nullable=True)
    market_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_swap: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_future: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    is_selected_for_data_collection: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    raw_market_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    exchange_credential = relationship("ExchangeCredential")
