from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.models.exchange_credential import ExchangeCredential
from app.models.exchange_market import ExchangeMarket
from app.models.market_micro_candle import MarketMicroCandle
from app.models.market_recent_trades_snapshot import MarketRecentTradesSnapshot
from app.models.ml_feature_snapshot import MlFeatureSnapshot
from app.models.ml_model import MlModel
from app.models.ml_snapshot_label import MlSnapshotLabel
from app.models.ml_training_session import MlTrainingSession


def get_ml_training_stats(snapshots_page: int = 1, snapshots_page_size: int = 10) -> dict:
    db = SessionLocal()
    try:
        snapshots_page_size = max(1, min(snapshots_page_size, 100))
        snapshots_page = max(1, snapshots_page)
        total_snapshots = db.scalar(select(func.count()).select_from(MlFeatureSnapshot)) or 0
        total_snapshot_pages = max(1, (total_snapshots + snapshots_page_size - 1) // snapshots_page_size)
        snapshots_page = min(snapshots_page, total_snapshot_pages)
        snapshots_offset = (snapshots_page - 1) * snapshots_page_size
        total_labels = db.scalar(select(func.count()).select_from(MlSnapshotLabel)) or 0
        pending_labels = db.scalar(
            select(func.count()).select_from(MlSnapshotLabel).where(MlSnapshotLabel.is_labeled.is_(False))
        ) or 0
        labeled_labels = db.scalar(
            select(func.count()).select_from(MlSnapshotLabel).where(MlSnapshotLabel.is_labeled.is_(True))
        ) or 0
        advanced_labels = db.scalar(
            select(func.count())
            .select_from(MlSnapshotLabel)
            .where(
                MlSnapshotLabel.long_mfe_percent.is_not(None),
                MlSnapshotLabel.long_mae_percent.is_not(None),
                MlSnapshotLabel.short_mfe_percent.is_not(None),
                MlSnapshotLabel.short_mae_percent.is_not(None),
            )
        ) or 0
        avg_long_mfe_30 = db.scalar(
            select(func.avg(MlSnapshotLabel.long_mfe_percent)).where(MlSnapshotLabel.horizon_seconds == 30)
        )
        avg_long_mae_30 = db.scalar(
            select(func.avg(MlSnapshotLabel.long_mae_percent)).where(MlSnapshotLabel.horizon_seconds == 30)
        )
        avg_short_mfe_30 = db.scalar(
            select(func.avg(MlSnapshotLabel.short_mfe_percent)).where(MlSnapshotLabel.horizon_seconds == 30)
        )
        avg_short_mae_30 = db.scalar(
            select(func.avg(MlSnapshotLabel.short_mae_percent)).where(MlSnapshotLabel.horizon_seconds == 30)
        )
        long_count = db.scalar(
            select(func.count()).select_from(MlSnapshotLabel).where(MlSnapshotLabel.direction_label == "long")
        ) or 0
        short_count = db.scalar(
            select(func.count()).select_from(MlSnapshotLabel).where(MlSnapshotLabel.direction_label == "short")
        ) or 0
        flat_count = db.scalar(
            select(func.count()).select_from(MlSnapshotLabel).where(MlSnapshotLabel.direction_label == "flat")
        ) or 0
        latest_captured_at = db.scalar(select(func.max(MlFeatureSnapshot.captured_at)))
        recent_trades_count = db.scalar(select(func.count()).select_from(MarketRecentTradesSnapshot)) or 0
        micro_candles_count = db.scalar(select(func.count()).select_from(MarketMicroCandle)) or 0
        average_data_quality_score = db.scalar(select(func.avg(MlFeatureSnapshot.data_quality_score)))
        latest_capture_latency_ms = db.scalar(
            select(MlFeatureSnapshot.capture_latency_ms)
            .order_by(MlFeatureSnapshot.captured_at.desc())
            .limit(1)
        )
        latest_missing_fields_count = db.scalar(
            select(MlFeatureSnapshot.missing_fields_count)
            .order_by(MlFeatureSnapshot.captured_at.desc())
            .limit(1)
        )
        active_session = db.scalar(
            select(MlTrainingSession)
            .where(MlTrainingSession.status == "running")
            .order_by(MlTrainingSession.started_at.desc())
            .limit(1)
        )
        last_error_session = db.scalar(
            select(MlTrainingSession)
            .where(MlTrainingSession.error_message.is_not(None))
            .order_by(MlTrainingSession.updated_at.desc())
            .limit(1)
        )
        active_pairs = list(
            db.execute(
                select(ExchangeCredential, ExchangeMarket)
                .join(ExchangeMarket, ExchangeMarket.exchange_credential_id == ExchangeCredential.id)
                .where(
                    ExchangeCredential.is_active.is_(True),
                    ExchangeMarket.is_active.is_(True),
                    ExchangeMarket.is_selected_for_data_collection.is_(True),
                )
                .order_by(ExchangeCredential.title, ExchangeMarket.symbol)
            )
        )
        snapshots_per_exchange = list(
            db.execute(
                select(MlFeatureSnapshot.exchange_code, func.count(MlFeatureSnapshot.id))
                .group_by(MlFeatureSnapshot.exchange_code)
                .order_by(MlFeatureSnapshot.exchange_code)
            )
        )
        snapshots_per_symbol = list(
            db.execute(
                select(MlFeatureSnapshot.symbol, func.count(MlFeatureSnapshot.id))
                .group_by(MlFeatureSnapshot.symbol)
                .order_by(MlFeatureSnapshot.symbol)
            )
        )
        models = list(db.scalars(select(MlModel).order_by(MlModel.trained_at.desc()).limit(20)))
        latest_feature_snapshots = list(
            db.scalars(
                select(MlFeatureSnapshot)
                .order_by(MlFeatureSnapshot.captured_at.desc())
                .offset(snapshots_offset)
                .limit(snapshots_page_size)
            )
        )
        snapshot_ids = [snapshot.id for snapshot in latest_feature_snapshots]
        labels_by_snapshot_id: dict[int, list[MlSnapshotLabel]] = {snapshot_id: [] for snapshot_id in snapshot_ids}
        if snapshot_ids:
            labels = list(
                db.scalars(
                    select(MlSnapshotLabel)
                    .where(MlSnapshotLabel.feature_snapshot_id.in_(snapshot_ids))
                    .order_by(MlSnapshotLabel.feature_snapshot_id, MlSnapshotLabel.horizon_seconds)
                )
            )
            for label in labels:
                labels_by_snapshot_id.setdefault(label.feature_snapshot_id, []).append(label)
        latest_feature_snapshot_rows = [
            {
                "snapshot": snapshot,
                "labels": labels_by_snapshot_id.get(snapshot.id, []),
                "advanced_ready": any(
                    label.long_mfe_percent is not None
                    and label.long_mae_percent is not None
                    and label.short_mfe_percent is not None
                    and label.short_mae_percent is not None
                    for label in labels_by_snapshot_id.get(snapshot.id, [])
                ),
            }
            for snapshot in latest_feature_snapshots
        ]

        return {
            "total_snapshots": total_snapshots,
            "total_labels": total_labels,
            "pending_labels": pending_labels,
            "labeled_labels": labeled_labels,
            "advanced_labels": advanced_labels,
            "avg_long_mfe_30": avg_long_mfe_30,
            "avg_long_mae_30": avg_long_mae_30,
            "avg_short_mfe_30": avg_short_mfe_30,
            "avg_short_mae_30": avg_short_mae_30,
            "long_count": long_count,
            "short_count": short_count,
            "flat_count": flat_count,
            "latest_captured_at": latest_captured_at,
            "recent_trades_count": recent_trades_count,
            "micro_candles_count": micro_candles_count,
            "average_data_quality_score": average_data_quality_score,
            "latest_capture_latency_ms": latest_capture_latency_ms,
            "latest_missing_fields_count": latest_missing_fields_count,
            "active_session": active_session,
            "last_runner_error": active_session.error_message
            if active_session and active_session.error_message
            else last_error_session.error_message
            if last_error_session
            else None,
            "active_pairs": active_pairs,
            "snapshots_per_exchange": snapshots_per_exchange,
            "snapshots_per_symbol": snapshots_per_symbol,
            "models": models,
            "latest_feature_snapshots": latest_feature_snapshots,
            "latest_feature_snapshot_rows": latest_feature_snapshot_rows,
            "snapshots_pagination": {
                "current_page": snapshots_page,
                "page_size": snapshots_page_size,
                "total_pages": total_snapshot_pages,
                "total_records": total_snapshots,
                "has_previous": snapshots_page > 1,
                "has_next": snapshots_page < total_snapshot_pages,
                "previous_page": max(1, snapshots_page - 1),
                "next_page": min(total_snapshot_pages, snapshots_page + 1),
            },
        }
    finally:
        db.close()
