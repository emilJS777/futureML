import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class MarketRecentTradesSnapshot(Base):
    __tablename__ = "market_recent_trades_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, index=True, nullable=False, default=uuid.uuid4
    )
    exchange_credential_id: Mapped[int] = mapped_column(ForeignKey("exchange_credentials.id"), nullable=False)
    exchange_market_id: Mapped[int] = mapped_column(ForeignKey("exchange_markets.id"), nullable=False)
    exchange_code: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str] = mapped_column(String(120), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    trades_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    trades_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    buy_volume: Mapped[Decimal | None] = mapped_column(Numeric(28, 12), nullable=True)
    sell_volume: Mapped[Decimal | None] = mapped_column(Numeric(28, 12), nullable=True)
    buy_sell_delta: Mapped[Decimal | None] = mapped_column(Numeric(28, 12), nullable=True)
    buy_sell_ratio: Mapped[Decimal | None] = mapped_column(Numeric(28, 12), nullable=True)
    avg_trade_size: Mapped[Decimal | None] = mapped_column(Numeric(28, 12), nullable=True)
    large_trade_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    largest_trade_size: Mapped[Decimal | None] = mapped_column(Numeric(28, 12), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    exchange_credential = relationship("ExchangeCredential")
    exchange_market = relationship("ExchangeMarket")
