import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class MarketMicroCandle(Base):
    __tablename__ = "market_micro_candles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, index=True, nullable=False, default=uuid.uuid4
    )
    exchange_credential_id: Mapped[int] = mapped_column(ForeignKey("exchange_credentials.id"), nullable=False)
    exchange_market_id: Mapped[int] = mapped_column(ForeignKey("exchange_markets.id"), nullable=False)
    exchange_code: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str] = mapped_column(String(120), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(16), nullable=False)
    open: Mapped[Decimal | None] = mapped_column(Numeric(28, 12), nullable=True)
    high: Mapped[Decimal | None] = mapped_column(Numeric(28, 12), nullable=True)
    low: Mapped[Decimal | None] = mapped_column(Numeric(28, 12), nullable=True)
    close: Mapped[Decimal | None] = mapped_column(Numeric(28, 12), nullable=True)
    volume: Mapped[Decimal | None] = mapped_column(Numeric(28, 12), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    raw_ohlcv_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    exchange_credential = relationship("ExchangeCredential")
    exchange_market = relationship("ExchangeMarket")
