import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, Numeric, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class MlShadowBacktest(Base):
    __tablename__ = "ml_shadow_backtests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, index=True, nullable=False, default=uuid.uuid4
    )
    ml_experiment_id: Mapped[int] = mapped_column(ForeignKey("ml_experiments.id"), nullable=False, index=True)
    horizon_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence_threshold: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    total_signals: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    long_signals: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    short_signals: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    flat_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    win_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    loss_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    win_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    avg_win_percent: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    avg_loss_percent: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    gross_profit_percent: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    gross_loss_percent: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    expectancy_percent: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    max_drawdown_percent: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    profit_factor: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    fees_percent: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False, default=Decimal("0.1"))
    slippage_percent: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False, default=Decimal("0.05"))
    net_expectancy_percent: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    equity_curve_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    results_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    experiment = relationship("MlExperiment", back_populates="shadow_backtests")
