import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.ml_feature_snapshot import MlFeatureSnapshot
from app.models.ml_snapshot_label import MlSnapshotLabel


logger = logging.getLogger(__name__)
TP_SL_THRESHOLDS = {
    "0_2": Decimal("0.2"),
    "0_3": Decimal("0.3"),
    "0_5": Decimal("0.5"),
    "1_0": Decimal("1.0"),
}


def _advanced_labels_ready(label: MlSnapshotLabel) -> bool:
    return (
        label.long_mfe_percent is not None
        and label.long_mae_percent is not None
        and label.short_mfe_percent is not None
        and label.short_mae_percent is not None
        and label.expected_long_return_percent is not None
        and label.expected_short_return_percent is not None
    )


def _apply_label_calculation(
    db,
    label: MlSnapshotLabel,
    snapshot: MlFeatureSnapshot,
    now: datetime,
    long_threshold: Decimal,
    short_threshold: Decimal,
) -> bool:
    if snapshot.captured_at + timedelta(seconds=label.horizon_seconds) > now:
        return False
    if snapshot.mid_price is None or snapshot.mid_price == 0:
        return False

    target_time = snapshot.captured_at + timedelta(seconds=label.horizon_seconds)
    future_snapshots = list(
        db.scalars(
            select(MlFeatureSnapshot)
            .where(
                MlFeatureSnapshot.exchange_credential_id == snapshot.exchange_credential_id,
                MlFeatureSnapshot.symbol == snapshot.symbol,
                MlFeatureSnapshot.captured_at > snapshot.captured_at,
                MlFeatureSnapshot.captured_at <= target_time,
                MlFeatureSnapshot.mid_price.is_not(None),
            )
            .order_by(MlFeatureSnapshot.captured_at.asc())
        )
    )
    if not future_snapshots:
        return False

    returns = [
        (future_snapshot.mid_price - snapshot.mid_price) / snapshot.mid_price * Decimal("100")
        for future_snapshot in future_snapshots
        if future_snapshot.mid_price is not None
    ]
    if not returns:
        return False

    final_snapshot = future_snapshots[-1]
    future_return = returns[-1]
    long_mfe = max(returns)
    long_mae = min(returns)
    short_mfe = abs(long_mae)
    short_mae = abs(long_mfe)

    if future_return >= long_threshold:
        direction = "long"
    elif future_return <= -short_threshold:
        direction = "short"
    else:
        direction = "flat"

    label.future_mid_price = final_snapshot.mid_price
    label.future_return_percent = future_return
    label.direction_label = direction
    label.long_would_win = future_return > 0
    label.short_would_win = future_return < 0
    label.long_mfe_percent = long_mfe
    label.long_mae_percent = long_mae
    label.short_mfe_percent = short_mfe
    label.short_mae_percent = short_mae

    for suffix, threshold in TP_SL_THRESHOLDS.items():
        setattr(label, f"long_tp_hit_{suffix}", long_mfe >= threshold)
        setattr(label, f"long_sl_hit_{suffix}", abs(long_mae) >= threshold)
        setattr(label, f"short_tp_hit_{suffix}", short_mfe >= threshold)
        setattr(label, f"short_sl_hit_{suffix}", short_mae >= threshold)

    label.best_long_tp_percent = long_mfe
    label.best_long_sl_percent = abs(long_mae)
    label.best_short_tp_percent = short_mfe
    label.best_short_sl_percent = short_mae
    label.expected_long_return_percent = future_return
    label.expected_short_return_percent = -future_return
    label.is_labeled = True
    label.labeled_at = now
    return True


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
            if _apply_label_calculation(db, label, snapshot, now, long_threshold, short_threshold):
                processed += 1
            else:
                skipped += 1

        db.commit()
        return {"processed": processed, "skipped": skipped}
    except Exception:
        logger.exception("Processing ML labels failed.")
        db.rollback()
        raise
    finally:
        db.close()


def backfill_advanced_labels(limit: int = 5000) -> dict[str, int]:
    db = SessionLocal()
    updated = 0
    skipped = 0
    try:
        now = datetime.now(UTC)
        settings = get_settings()
        long_threshold = Decimal(str(settings.label_long_threshold_percent))
        short_threshold = Decimal(str(settings.label_short_threshold_percent))
        labels = list(
            db.scalars(
                select(MlSnapshotLabel)
                .join(MlFeatureSnapshot, MlFeatureSnapshot.id == MlSnapshotLabel.feature_snapshot_id)
                .where(MlSnapshotLabel.is_labeled.is_(True))
                .order_by(MlSnapshotLabel.created_at)
                .limit(limit)
            )
        )

        for label in labels:
            if _advanced_labels_ready(label):
                skipped += 1
                continue
            if _apply_label_calculation(db, label, label.feature_snapshot, now, long_threshold, short_threshold):
                updated += 1
            else:
                skipped += 1

        db.commit()
        return {"updated": updated, "skipped": skipped}
    except Exception:
        logger.exception("Backfilling advanced ML labels failed.")
        db.rollback()
        raise
    finally:
        db.close()
