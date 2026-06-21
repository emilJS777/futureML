import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.ml_feature_snapshot import MlFeatureSnapshot
from app.models.ml_snapshot_label import MlSnapshotLabel


logger = logging.getLogger(__name__)


def process_pending_labels() -> dict[str, int]:
    db = SessionLocal()
    processed = 0
    skipped = 0
    try:
        now = datetime.now(UTC)
        labels = list(
            db.scalars(
                select(MlSnapshotLabel)
                .join(MlFeatureSnapshot, MlFeatureSnapshot.id == MlSnapshotLabel.feature_snapshot_id)
                .where(MlSnapshotLabel.is_labeled.is_(False))
                .order_by(MlSnapshotLabel.created_at)
                .limit(1000)
            )
        )
        settings = get_settings()
        long_threshold = Decimal(str(settings.label_long_threshold_percent))
        short_threshold = Decimal(str(settings.label_short_threshold_percent))

        for label in labels:
            snapshot = label.feature_snapshot
            if snapshot.captured_at + timedelta(seconds=label.horizon_seconds) > now:
                skipped += 1
                continue
            if snapshot.mid_price is None or snapshot.mid_price == 0:
                skipped += 1
                continue

            target_time = snapshot.captured_at + timedelta(seconds=label.horizon_seconds)
            future_snapshot = db.scalar(
                select(MlFeatureSnapshot)
                .where(
                    MlFeatureSnapshot.exchange_credential_id == snapshot.exchange_credential_id,
                    MlFeatureSnapshot.symbol == snapshot.symbol,
                    MlFeatureSnapshot.captured_at >= target_time,
                    MlFeatureSnapshot.mid_price.is_not(None),
                )
                .order_by(MlFeatureSnapshot.captured_at.asc())
                .limit(1)
            )
            if future_snapshot is None or future_snapshot.mid_price is None:
                skipped += 1
                continue

            future_return = (future_snapshot.mid_price - snapshot.mid_price) / snapshot.mid_price * Decimal("100")
            if future_return >= long_threshold:
                direction = "long"
            elif future_return <= -short_threshold:
                direction = "short"
            else:
                direction = "flat"

            label.future_mid_price = future_snapshot.mid_price
            label.future_return_percent = future_return
            label.direction_label = direction
            label.long_would_win = future_return > 0
            label.short_would_win = future_return < 0
            label.is_labeled = True
            label.labeled_at = now
            processed += 1

        db.commit()
        return {"processed": processed, "skipped": skipped}
    except Exception:
        logger.exception("Processing ML labels failed.")
        db.rollback()
        raise
    finally:
        db.close()
