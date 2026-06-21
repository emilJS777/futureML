import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Integer, JSON, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MlModel(Base):
    __tablename__ = "ml_models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, index=True, nullable=False, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    model_type: Mapped[str] = mapped_column(String(80), nullable=False)
    target_horizon_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    train_rows_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    accuracy: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    precision_long: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    precision_short: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    precision_flat: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    model_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    feature_columns_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    metrics_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
