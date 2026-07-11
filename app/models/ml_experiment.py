import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Integer, JSON, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class MlExperiment(Base):
    __tablename__ = "ml_experiments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, index=True, nullable=False, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    progress_stage: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    model_type: Mapped[str] = mapped_column(String(80), nullable=False)
    target_type: Mapped[str] = mapped_column(String(80), nullable=False, default="direction_label")
    horizon_seconds: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    confidence_threshold: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    min_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    train_rows_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    test_rows_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    accuracy: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    precision_long: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    precision_short: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    precision_flat: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    recall_long: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    recall_short: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    recall_flat: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    f1_long: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    f1_short: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    f1_flat: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    confusion_matrix_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    feature_importance_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    classification_report_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    model_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    shadow_backtests = relationship(
        "MlShadowBacktest",
        back_populates="experiment",
        cascade="all, delete-orphan",
        order_by="MlShadowBacktest.created_at.desc()",
    )
