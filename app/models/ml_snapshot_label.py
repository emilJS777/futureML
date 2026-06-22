import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class MlSnapshotLabel(Base):
    __tablename__ = "ml_snapshot_labels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, index=True, nullable=False, default=uuid.uuid4
    )
    feature_snapshot_id: Mapped[int] = mapped_column(ForeignKey("ml_feature_snapshots.id"), nullable=False)
    horizon_seconds: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    future_mid_price: Mapped[Decimal | None] = mapped_column(Numeric(28, 12), nullable=True)
    future_return_percent: Mapped[Decimal | None] = mapped_column(Numeric(28, 12), nullable=True)
    direction_label: Mapped[str | None] = mapped_column(String(16), nullable=True)
    long_would_win: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    short_would_win: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    long_mfe_percent: Mapped[Decimal | None] = mapped_column(Numeric(28, 12), nullable=True)
    long_mae_percent: Mapped[Decimal | None] = mapped_column(Numeric(28, 12), nullable=True)
    short_mfe_percent: Mapped[Decimal | None] = mapped_column(Numeric(28, 12), nullable=True)
    short_mae_percent: Mapped[Decimal | None] = mapped_column(Numeric(28, 12), nullable=True)
    long_tp_hit_0_2: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    long_sl_hit_0_2: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    short_tp_hit_0_2: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    short_sl_hit_0_2: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    long_tp_hit_0_3: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    long_sl_hit_0_3: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    short_tp_hit_0_3: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    short_sl_hit_0_3: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    long_tp_hit_0_5: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    long_sl_hit_0_5: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    short_tp_hit_0_5: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    short_sl_hit_0_5: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    long_tp_hit_1_0: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    long_sl_hit_1_0: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    short_tp_hit_1_0: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    short_sl_hit_1_0: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    best_long_tp_percent: Mapped[Decimal | None] = mapped_column(Numeric(28, 12), nullable=True)
    best_short_tp_percent: Mapped[Decimal | None] = mapped_column(Numeric(28, 12), nullable=True)
    best_long_sl_percent: Mapped[Decimal | None] = mapped_column(Numeric(28, 12), nullable=True)
    best_short_sl_percent: Mapped[Decimal | None] = mapped_column(Numeric(28, 12), nullable=True)
    expected_long_return_percent: Mapped[Decimal | None] = mapped_column(Numeric(28, 12), nullable=True)
    expected_short_return_percent: Mapped[Decimal | None] = mapped_column(Numeric(28, 12), nullable=True)
    is_labeled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    labeled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    feature_snapshot = relationship("MlFeatureSnapshot")
