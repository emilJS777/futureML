import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class MarketDataSnapshot(Base):
    __tablename__ = "market_data_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, index=True, nullable=False, default=uuid.uuid4
    )
    exchange_credential_id: Mapped[int] = mapped_column(ForeignKey("exchange_credentials.id"), nullable=False)
    exchange_market_id: Mapped[int | None] = mapped_column(ForeignKey("exchange_markets.id"), nullable=True)
    exchange_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    best_bid: Mapped[Decimal | None] = mapped_column(Numeric(28, 12), nullable=True)
    best_ask: Mapped[Decimal | None] = mapped_column(Numeric(28, 12), nullable=True)
    spread: Mapped[Decimal | None] = mapped_column(Numeric(28, 12), nullable=True)
    spread_percent: Mapped[Decimal | None] = mapped_column(Numeric(28, 12), nullable=True)
    mid_price: Mapped[Decimal | None] = mapped_column(Numeric(28, 12), nullable=True)
    last_price: Mapped[Decimal | None] = mapped_column(Numeric(28, 12), nullable=True)
    mark_price: Mapped[Decimal | None] = mapped_column(Numeric(28, 12), nullable=True)
    index_price: Mapped[Decimal | None] = mapped_column(Numeric(28, 12), nullable=True)
    funding_rate: Mapped[Decimal | None] = mapped_column(Numeric(28, 12), nullable=True)
    next_funding_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    open_interest: Mapped[Decimal | None] = mapped_column(Numeric(28, 12), nullable=True)
    volume_24h: Mapped[Decimal | None] = mapped_column(Numeric(28, 12), nullable=True)
    quote_volume_24h: Mapped[Decimal | None] = mapped_column(Numeric(28, 12), nullable=True)
    price_change_percent_24h: Mapped[Decimal | None] = mapped_column(Numeric(28, 12), nullable=True)
    order_book_bids_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    order_book_asks_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    order_book_depth: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    raw_ticker_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    raw_funding_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    raw_open_interest_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    exchange_credential = relationship("ExchangeCredential")
    exchange_market = relationship("ExchangeMarket")
