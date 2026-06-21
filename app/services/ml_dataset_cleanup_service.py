from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, select, update

from app.core.database import SessionLocal
from app.models.market_micro_candle import MarketMicroCandle
from app.models.market_recent_trades_snapshot import MarketRecentTradesSnapshot
from app.models.ml_feature_snapshot import MlFeatureSnapshot
from app.models.ml_model import MlModel
from app.models.ml_snapshot_label import MlSnapshotLabel
from app.models.ml_training_session import MlTrainingSession


def _delete_model_files(model_paths: list[str]) -> int:
    model_dir = Path("storage/models").resolve()
    deleted_files = 0

    for raw_path in model_paths:
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        resolved = candidate.resolve()

        if model_dir not in resolved.parents:
            continue
        if resolved.is_file():
            resolved.unlink()
            deleted_files += 1

    return deleted_files


def delete_ml_dataset(delete_models: bool = False) -> dict:
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        stopped_sessions = (
            db.execute(
                update(MlTrainingSession)
                .where(MlTrainingSession.status == "running")
                .values(status="stopped", stopped_at=now)
            ).rowcount
            or 0
        )

        deleted_labels = db.execute(delete(MlSnapshotLabel)).rowcount or 0
        deleted_feature_snapshots = db.execute(delete(MlFeatureSnapshot)).rowcount or 0
        deleted_recent_trades = db.execute(delete(MarketRecentTradesSnapshot)).rowcount or 0
        deleted_micro_candles = db.execute(delete(MarketMicroCandle)).rowcount or 0

        deleted_models = 0
        deleted_model_files = 0
        if delete_models:
            model_paths = [
                model_path
                for model_path in db.scalars(select(MlModel.model_path).where(MlModel.model_path.is_not(None)))
                if model_path
            ]
            deleted_models = db.execute(delete(MlModel)).rowcount or 0
            deleted_model_files = _delete_model_files(model_paths)

        db.commit()

        return {
            "stopped_sessions": stopped_sessions,
            "deleted_labels": deleted_labels,
            "deleted_feature_snapshots": deleted_feature_snapshots,
            "deleted_recent_trades": deleted_recent_trades,
            "deleted_micro_candles": deleted_micro_candles,
            "deleted_models": deleted_models,
            "deleted_model_files": deleted_model_files,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
