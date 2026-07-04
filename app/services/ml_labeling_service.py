import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import selectinload

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
DEFAULT_BACKFILL_HORIZONS = (10, 30, 60)
SKIP_REASON_KEYS = (
    "no_snapshot",
    "snapshot_null_mid_price",
    "no_future_snapshots_in_horizon_window",
    "future_snapshots_null_mid_price",
    "not_mature_yet",
    "db_update_error",
    "already_labeled",
    "other",
)


def _skip_reason_counts() -> dict[str, int]:
    return {reason: 0 for reason in SKIP_REASON_KEYS}


def _pending_label_ready_filter(now: datetime, safety_seconds: int):
    return or_(
        *(
            and_(
                MlSnapshotLabel.horizon_seconds == horizon,
                MlFeatureSnapshot.captured_at <= now - timedelta(seconds=horizon + safety_seconds),
            )
            for horizon in DEFAULT_BACKFILL_HORIZONS
        )
    )


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
    snapshot: MlFeatureSnapshot | None,
    now: datetime,
    long_threshold: Decimal,
    short_threshold: Decimal,
    safety_seconds: int = 0,
    future_lookup_tolerance_seconds: int = 0,
) -> tuple[bool, str | None]:
    if label.is_labeled and _advanced_labels_ready(label):
        return False, "already_labeled"
    if snapshot is None:
        return False, "no_snapshot"
    if snapshot.captured_at + timedelta(seconds=label.horizon_seconds + safety_seconds) > now:
        return False, "not_mature_yet"
    if snapshot.mid_price is None or snapshot.mid_price == 0:
        return False, "snapshot_null_mid_price"

    target_time = snapshot.captured_at + timedelta(seconds=label.horizon_seconds)
    future_prices = list(
        db.execute(
            select(MlFeatureSnapshot.mid_price)
            .where(
                MlFeatureSnapshot.exchange_credential_id == snapshot.exchange_credential_id,
                MlFeatureSnapshot.symbol == snapshot.symbol,
                MlFeatureSnapshot.captured_at > snapshot.captured_at,
                MlFeatureSnapshot.captured_at <= target_time,
            )
            .order_by(MlFeatureSnapshot.captured_at.asc())
        )
    )
    if not future_prices:
        tolerance_end = target_time + timedelta(seconds=future_lookup_tolerance_seconds)
        future_prices = list(
            db.execute(
                select(MlFeatureSnapshot.mid_price)
                .where(
                    MlFeatureSnapshot.exchange_credential_id == snapshot.exchange_credential_id,
                    MlFeatureSnapshot.symbol == snapshot.symbol,
                    MlFeatureSnapshot.captured_at > target_time,
                    MlFeatureSnapshot.captured_at <= tolerance_end,
                )
                .order_by(MlFeatureSnapshot.captured_at.asc())
                .limit(1)
            )
        )
        if not future_prices:
            return False, "no_future_snapshots_in_horizon_window"

    valid_future_prices = [future_price[0] for future_price in future_prices if future_price[0] is not None]
    if not valid_future_prices:
        return False, "future_snapshots_null_mid_price"

    returns = [
        (future_mid_price - snapshot.mid_price) / snapshot.mid_price * Decimal("100")
        for future_mid_price in valid_future_prices
    ]
    final_mid_price = valid_future_prices[-1]
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

    label.future_mid_price = final_mid_price
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
    return True, None


def process_pending_labels() -> dict[str, int]:
    return backfill_pending_labels_in_batches(batch_size=1000, max_batches=1)


def count_eligible_pending_labels() -> int:
    db = SessionLocal()
    try:
        now = datetime.now(UTC)
        settings = get_settings()
        return db.scalar(
            select(func.count())
            .select_from(MlSnapshotLabel)
            .join(MlFeatureSnapshot, MlFeatureSnapshot.id == MlSnapshotLabel.feature_snapshot_id)
            .where(
                MlSnapshotLabel.is_labeled.is_(False),
                _pending_label_ready_filter(now, settings.label_backfill_safety_seconds),
            )
        ) or 0
    finally:
        db.close()


def count_incomplete_advanced_labels() -> int:
    db = SessionLocal()
    try:
        return db.scalar(
            select(func.count())
            .select_from(MlSnapshotLabel)
            .where(
                MlSnapshotLabel.is_labeled.is_(True),
                or_(
                    MlSnapshotLabel.long_mfe_percent.is_(None),
                    MlSnapshotLabel.long_mae_percent.is_(None),
                    MlSnapshotLabel.short_mfe_percent.is_(None),
                    MlSnapshotLabel.short_mae_percent.is_(None),
                    MlSnapshotLabel.expected_long_return_percent.is_(None),
                    MlSnapshotLabel.expected_short_return_percent.is_(None),
                ),
            )
        ) or 0
    finally:
        db.close()


def backfill_pending_labels_in_batches(batch_size: int = 1000, max_batches: int = 10) -> dict[str, int]:
    batch_size = max(1, min(batch_size, 5000))
    max_batches = max(1, min(max_batches, 100))
    db = SessionLocal()
    processed = 0
    skipped = 0
    batches_run = 0
    skipped_label_ids: set[int] = set()
    skip_reasons = _skip_reason_counts()
    try:
        settings = get_settings()
        long_threshold = Decimal(str(settings.label_long_threshold_percent))
        short_threshold = Decimal(str(settings.label_short_threshold_percent))
        safety_seconds = max(0, int(settings.label_backfill_safety_seconds))
        future_lookup_tolerance_seconds = max(0, int(settings.label_future_lookup_tolerance_seconds))

        for _ in range(max_batches):
            now = datetime.now(UTC)
            query = (
                select(MlSnapshotLabel)
                .options(selectinload(MlSnapshotLabel.feature_snapshot))
                .join(MlFeatureSnapshot, MlFeatureSnapshot.id == MlSnapshotLabel.feature_snapshot_id)
                .where(
                    MlSnapshotLabel.is_labeled.is_(False),
                    _pending_label_ready_filter(now, safety_seconds),
                )
                .order_by(MlFeatureSnapshot.captured_at.asc(), MlSnapshotLabel.horizon_seconds.asc())
                .limit(batch_size)
            )
            if skipped_label_ids:
                query = query.where(MlSnapshotLabel.id.not_in(skipped_label_ids))
            labels = list(db.scalars(query))
            if not labels:
                break

            batch_processed = 0
            batch_skipped = 0
            for label in labels:
                try:
                    did_process, reason = _apply_label_calculation(
                        db,
                        label,
                        label.feature_snapshot,
                        now,
                        long_threshold,
                        short_threshold,
                        safety_seconds=safety_seconds,
                        future_lookup_tolerance_seconds=future_lookup_tolerance_seconds,
                    )
                except Exception:
                    logger.exception("ML label backfill failed for label_id=%s.", label.id)
                    skip_reasons["db_update_error"] += 1
                    batch_skipped += 1
                    skipped_label_ids.add(label.id)
                    continue

                if did_process:
                    batch_processed += 1
                else:
                    reason = reason if reason in skip_reasons else "other"
                    skip_reasons[reason] += 1
                    batch_skipped += 1
                    skipped_label_ids.add(label.id)

            db.commit()
            batches_run += 1
            processed += batch_processed
            skipped += batch_skipped
            logger.info(
                "ML pending label backfill batch complete: batch=%s processed=%s skipped=%s total_processed=%s skip_reasons=%s.",
                batches_run,
                batch_processed,
                batch_skipped,
                processed,
                skip_reasons,
            )
            if batch_processed == 0:
                break

        remaining_pending = db.scalar(
            select(func.count()).select_from(MlSnapshotLabel).where(MlSnapshotLabel.is_labeled.is_(False))
        ) or 0
        remaining_eligible_pending = db.scalar(
            select(func.count())
            .select_from(MlSnapshotLabel)
            .join(MlFeatureSnapshot, MlFeatureSnapshot.id == MlSnapshotLabel.feature_snapshot_id)
            .where(
                MlSnapshotLabel.is_labeled.is_(False),
                _pending_label_ready_filter(datetime.now(UTC), safety_seconds),
            )
        ) or 0
        return {
            "processed": processed,
            "skipped": skipped,
            "batches_run": batches_run,
            "batch_size": batch_size,
            "remaining_pending": remaining_pending,
            "remaining_eligible_pending": remaining_eligible_pending,
            "skip_reasons": skip_reasons,
            "safety_seconds": safety_seconds,
            "future_lookup_tolerance_seconds": future_lookup_tolerance_seconds,
        }
    except Exception:
        logger.exception("Backfilling pending ML labels failed.")
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
        safety_seconds = max(0, int(settings.label_backfill_safety_seconds))
        future_lookup_tolerance_seconds = max(0, int(settings.label_future_lookup_tolerance_seconds))
        labels = list(
            db.scalars(
                select(MlSnapshotLabel)
                .options(selectinload(MlSnapshotLabel.feature_snapshot))
                .join(MlFeatureSnapshot, MlFeatureSnapshot.id == MlSnapshotLabel.feature_snapshot_id)
                .where(
                    MlSnapshotLabel.is_labeled.is_(True),
                    or_(
                        MlSnapshotLabel.long_mfe_percent.is_(None),
                        MlSnapshotLabel.long_mae_percent.is_(None),
                        MlSnapshotLabel.short_mfe_percent.is_(None),
                        MlSnapshotLabel.short_mae_percent.is_(None),
                        MlSnapshotLabel.expected_long_return_percent.is_(None),
                        MlSnapshotLabel.expected_short_return_percent.is_(None),
                    ),
                )
                .order_by(MlSnapshotLabel.created_at)
                .limit(limit)
            )
        )

        for label in labels:
            if _advanced_labels_ready(label):
                skipped += 1
                continue
            did_process, _reason = _apply_label_calculation(
                db,
                label,
                label.feature_snapshot,
                now,
                long_threshold,
                short_threshold,
                safety_seconds=safety_seconds,
                future_lookup_tolerance_seconds=future_lookup_tolerance_seconds,
            )
            if did_process:
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
