from datetime import UTC, datetime, timedelta
from decimal import Decimal
import logging
from pathlib import Path
import threading

from sqlalchemy import and_, distinct, func, or_, select

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.ml_experiment import MlExperiment
from app.models.ml_feature_snapshot import MlFeatureSnapshot
from app.models.ml_snapshot_label import MlSnapshotLabel
from app.services.ml_training_service import FEATURE_COLUMNS


CLASS_LABELS = ["long", "short", "flat"]
SUPPORTED_MODEL_TYPES = {"random_forest", "gradient_boosting"}
PROBABILITY_THRESHOLDS = [0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.9]
EXPERIMENT_HORIZONS = (10, 30, 60)
MIN_EXPERIMENT_DATA_QUALITY_SCORE = 60
logger = logging.getLogger(__name__)


def _to_decimal(value: float | None) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


def _set_class_metrics(experiment: MlExperiment, report: dict) -> None:
    for label in CLASS_LABELS:
        metrics = report.get(label, {})
        setattr(experiment, f"precision_{label}", _to_decimal(metrics.get("precision")))
        setattr(experiment, f"recall_{label}", _to_decimal(metrics.get("recall")))
        setattr(experiment, f"f1_{label}", _to_decimal(metrics.get("f1-score")))


def _count_query(db, query) -> int:
    return db.scalar(query) or 0


def _feature_null_filter():
    return or_(*(getattr(MlFeatureSnapshot, column).is_(None) for column in FEATURE_COLUMNS))


def _format_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _training_label_conditions(horizon_seconds: int) -> tuple:
    return (
        MlSnapshotLabel.horizon_seconds == horizon_seconds,
        MlSnapshotLabel.is_labeled.is_(True),
        MlSnapshotLabel.direction_label.is_not(None),
        MlSnapshotLabel.future_return_percent.is_not(None),
    )


def _build_training_dataset_diagnostics(db, horizon_seconds: int, final_dataframe_rows: int | None = None) -> dict:
    valid_label_conditions = _training_label_conditions(horizon_seconds)
    joined_base = (
        select(MlSnapshotLabel.id, MlFeatureSnapshot.id.label("feature_snapshot_id"))
        .join(MlFeatureSnapshot, MlFeatureSnapshot.id == MlSnapshotLabel.feature_snapshot_id)
        .where(MlSnapshotLabel.horizon_seconds == horizon_seconds)
        .subquery()
    )
    labeled_joined_base = (
        select(MlSnapshotLabel.id, MlFeatureSnapshot.id.label("feature_snapshot_id"))
        .join(MlFeatureSnapshot, MlFeatureSnapshot.id == MlSnapshotLabel.feature_snapshot_id)
        .where(*valid_label_conditions)
        .subquery()
    )
    quality_base = (
        select(
            MlSnapshotLabel.id.label("label_id"),
            MlFeatureSnapshot.id.label("feature_snapshot_id"),
            MlFeatureSnapshot.captured_at,
        )
        .join(MlFeatureSnapshot, MlFeatureSnapshot.id == MlSnapshotLabel.feature_snapshot_id)
        .where(
            *valid_label_conditions,
            MlFeatureSnapshot.data_quality_score >= MIN_EXPERIMENT_DATA_QUALITY_SCORE,
        )
        .subquery()
    )
    rows_after_quality = _count_query(db, select(func.count()).select_from(quality_base))
    distinct_after_quality = _count_query(
        db,
        select(func.count(distinct(quality_base.c.feature_snapshot_id))).select_from(quality_base),
    )
    min_captured_at, max_captured_at = db.execute(
        select(func.min(quality_base.c.captured_at), func.max(quality_base.c.captured_at))
    ).one()
    latest_snapshot_captured_at = db.scalar(select(func.max(MlFeatureSnapshot.captured_at)))
    total_labels_for_horizon = _count_query(
        db,
        select(func.count()).select_from(MlSnapshotLabel).where(MlSnapshotLabel.horizon_seconds == horizon_seconds),
    )
    labeled_labels_for_horizon = _count_query(
        db,
        select(func.count()).select_from(MlSnapshotLabel).where(*valid_label_conditions),
    )
    labels_joined_to_feature_snapshots = _count_query(
        db,
        select(func.count()).select_from(joined_base),
    )
    labeled_labels_joined_to_feature_snapshots = _count_query(
        db,
        select(func.count()).select_from(labeled_joined_base),
    )
    diagnostics = {
        "horizon_seconds": horizon_seconds,
        "data_quality_threshold": MIN_EXPERIMENT_DATA_QUALITY_SCORE,
        "total_feature_snapshots": _count_query(db, select(func.count()).select_from(MlFeatureSnapshot)),
        "total_labels_for_selected_horizon": total_labels_for_horizon,
        "labeled_labels_for_selected_horizon": labeled_labels_for_horizon,
        "labels_joined_to_feature_snapshots": labels_joined_to_feature_snapshots,
        "labeled_labels_joined_to_feature_snapshots": labeled_labels_joined_to_feature_snapshots,
        "rows_after_data_quality_filter": rows_after_quality,
        "distinct_feature_snapshots_after_data_quality_filter": distinct_after_quality,
        "duplicate_label_rows_after_data_quality_filter": max(rows_after_quality - distinct_after_quality, 0),
        "final_dataframe_rows": final_dataframe_rows if final_dataframe_rows is not None else rows_after_quality,
        "training_min_captured_at": _format_datetime(min_captured_at),
        "training_max_captured_at": _format_datetime(max_captured_at),
        "latest_snapshot_captured_at_in_database": _format_datetime(latest_snapshot_captured_at),
        "filters_applied": [
            f"horizon_seconds == {horizon_seconds}",
            "is_labeled == true",
            "direction_label is not null",
            "future_return_percent is not null",
            f"data_quality_score >= {MIN_EXPERIMENT_DATA_QUALITY_SCORE}",
        ],
        "filters_not_applied": [
            "no hardcoded row limit",
            "no captured_at date range filter",
            "no training_session_id/session filter",
        ],
    }
    return diagnostics


def _build_horizon_eligibility(db, horizon: int, total_feature_snapshots: int) -> dict:
    valid_label_conditions = _training_label_conditions(horizon)
    labeled_rows = _count_query(
        db,
        select(func.count())
        .select_from(MlSnapshotLabel)
        .where(*valid_label_conditions),
    )
    missing_label_rows = _count_query(
        db,
        select(func.count())
        .select_from(MlFeatureSnapshot)
        .outerjoin(
            MlSnapshotLabel,
            (MlSnapshotLabel.feature_snapshot_id == MlFeatureSnapshot.id)
            & (MlSnapshotLabel.horizon_seconds == horizon),
        )
        .where(
            or_(
                MlSnapshotLabel.id.is_(None),
                MlSnapshotLabel.is_labeled.is_not(True),
                MlSnapshotLabel.direction_label.is_(None),
                MlSnapshotLabel.future_return_percent.is_(None),
            )
        ),
    )
    data_quality_excluded_rows = _count_query(
        db,
        select(func.count())
        .select_from(MlSnapshotLabel)
        .join(MlFeatureSnapshot, MlFeatureSnapshot.id == MlSnapshotLabel.feature_snapshot_id)
        .where(
            *valid_label_conditions,
            or_(
                MlFeatureSnapshot.data_quality_score.is_(None),
                MlFeatureSnapshot.data_quality_score < MIN_EXPERIMENT_DATA_QUALITY_SCORE,
            ),
        ),
    )
    eligible_query = (
        select(func.count())
        .select_from(MlSnapshotLabel)
        .join(MlFeatureSnapshot, MlFeatureSnapshot.id == MlSnapshotLabel.feature_snapshot_id)
        .where(
            *valid_label_conditions,
            MlFeatureSnapshot.data_quality_score >= MIN_EXPERIMENT_DATA_QUALITY_SCORE,
        )
    )
    final_eligible_rows = _count_query(db, eligible_query)
    rows_with_null_feature_values = _count_query(
        db,
        select(func.count())
        .select_from(MlSnapshotLabel)
        .join(MlFeatureSnapshot, MlFeatureSnapshot.id == MlSnapshotLabel.feature_snapshot_id)
        .where(
            *valid_label_conditions,
            MlFeatureSnapshot.data_quality_score >= MIN_EXPERIMENT_DATA_QUALITY_SCORE,
            _feature_null_filter(),
        ),
    )
    train_rows = int(final_eligible_rows * 0.7)
    test_rows = final_eligible_rows - train_rows
    return {
        "horizon": horizon,
        "total_feature_snapshots": total_feature_snapshots,
        "total_labels": _count_query(
            db,
            select(func.count()).select_from(MlSnapshotLabel).where(MlSnapshotLabel.horizon_seconds == horizon),
        ),
        "total_labeled_rows": labeled_rows,
        "rows_excluded_by_missing_labels": missing_label_rows,
        "rows_excluded_by_data_quality_filter": data_quality_excluded_rows,
        "rows_excluded_by_null_feature_values": 0,
        "rows_with_null_feature_values": rows_with_null_feature_values,
        "final_eligible_training_rows": final_eligible_rows,
        "estimated_train_rows": train_rows,
        "estimated_test_rows": test_rows,
    }


def get_dataset_eligibility_diagnostics() -> dict:
    db = SessionLocal()
    try:
        total_feature_snapshots = _count_query(
            db,
            select(func.count()).select_from(MlFeatureSnapshot),
        )
        total_labels = _count_query(
            db,
            select(func.count()).select_from(MlSnapshotLabel),
        )
        by_horizon = {
            horizon: _build_horizon_eligibility(db, horizon, total_feature_snapshots)
            for horizon in EXPERIMENT_HORIZONS
        }
        return {
            "total_feature_snapshots": total_feature_snapshots,
            "total_labels": total_labels,
            "by_horizon": by_horizon,
            "data_quality_threshold": MIN_EXPERIMENT_DATA_QUALITY_SCORE,
            "feature_columns_count": len(FEATURE_COLUMNS),
            "null_feature_policy": "Current experiment training keeps eligible rows and fills null feature values with 0.",
        }
    finally:
        db.close()


def get_experiment_dashboard_data() -> dict:
    db = SessionLocal()
    try:
        labeled_by_horizon = {
            horizon: db.scalar(
                select(func.count())
                .select_from(MlSnapshotLabel)
                .join(MlFeatureSnapshot, MlFeatureSnapshot.id == MlSnapshotLabel.feature_snapshot_id)
                .where(
                    MlSnapshotLabel.horizon_seconds == horizon,
                    MlSnapshotLabel.is_labeled.is_(True),
                    MlSnapshotLabel.direction_label.is_not(None),
                    MlSnapshotLabel.future_return_percent.is_not(None),
                    MlFeatureSnapshot.data_quality_score >= MIN_EXPERIMENT_DATA_QUALITY_SCORE,
                )
            )
            or 0
            for horizon in EXPERIMENT_HORIZONS
        }
        advanced_labels_count = db.scalar(
            select(func.count())
            .select_from(MlSnapshotLabel)
            .where(
                MlSnapshotLabel.is_labeled.is_(True),
                MlSnapshotLabel.long_mfe_percent.is_not(None),
                MlSnapshotLabel.long_mae_percent.is_not(None),
                MlSnapshotLabel.short_mfe_percent.is_not(None),
                MlSnapshotLabel.short_mae_percent.is_not(None),
            )
        ) or 0
        return {
            "labeled_by_horizon": labeled_by_horizon,
            "advanced_labels_count": advanced_labels_count,
            "latest_snapshot_at": db.scalar(select(func.max(MlFeatureSnapshot.captured_at))),
            "experiments": list(
                db.scalars(select(MlExperiment).order_by(MlExperiment.created_at.desc()).limit(100))
            ),
        }
    finally:
        db.close()


def _build_probability_diagnostics(rows, probabilities, predicted_classes) -> dict:
    import numpy as np

    class_names = [str(value) for value in predicted_classes]
    predictions = []
    for (snapshot, label), row_probabilities in zip(rows, probabilities, strict=True):
        best_index = int(np.argmax(row_probabilities))
        predicted_label = class_names[best_index]
        actual_label = str(label.direction_label)
        probability_by_class = {
            class_name: float(row_probabilities[index])
            for index, class_name in enumerate(class_names)
        }
        predictions.append(
            {
                "snapshot_public_id": str(snapshot.public_id),
                "captured_at": snapshot.captured_at,
                "exchange_code": snapshot.exchange_code,
                "symbol": snapshot.symbol,
                "predicted_label": predicted_label,
                "actual_label": actual_label,
                "is_correct": predicted_label == actual_label,
                "max_probability": float(row_probabilities[best_index]),
                "long_probability": probability_by_class.get("long", 0.0),
                "short_probability": probability_by_class.get("short", 0.0),
                "flat_probability": probability_by_class.get("flat", 0.0),
                "future_return_percent": float(label.future_return_percent)
                if label.future_return_percent is not None
                else None,
            }
        )

    max_probabilities = np.asarray([row["max_probability"] for row in predictions], dtype=float)
    histogram_edges = np.linspace(0, 1, 11)
    histogram_counts, _ = np.histogram(max_probabilities, bins=histogram_edges)
    histogram = [
        {
            "start": float(histogram_edges[index]),
            "end": float(histogram_edges[index + 1]),
            "count": int(count),
        }
        for index, count in enumerate(histogram_counts)
    ]
    max_histogram_count = max((item["count"] for item in histogram), default=0)
    for item in histogram:
        item["width_percent"] = (
            (item["count"] / max_histogram_count) * 100 if max_histogram_count else 0
        )

    threshold_counts = []
    for threshold in PROBABILITY_THRESHOLDS:
        above = [row for row in predictions if row["max_probability"] >= threshold]
        actionable = [row for row in above if row["predicted_label"] in {"long", "short"}]
        threshold_counts.append(
            {
                "threshold": threshold,
                "all_rows": len(above),
                "actionable_rows": len(actionable),
                "flat_rows": len(above) - len(actionable),
                "long_rows": sum(row["predicted_label"] == "long" for row in actionable),
                "short_rows": sum(row["predicted_label"] == "short" for row in actionable),
            }
        )

    distribution = {
        "count": len(predictions),
        "minimum": float(np.min(max_probabilities)) if len(max_probabilities) else None,
        "mean": float(np.mean(max_probabilities)) if len(max_probabilities) else None,
        "p25": float(np.percentile(max_probabilities, 25)) if len(max_probabilities) else None,
        "median": float(np.median(max_probabilities)) if len(max_probabilities) else None,
        "p75": float(np.percentile(max_probabilities, 75)) if len(max_probabilities) else None,
        "p90": float(np.percentile(max_probabilities, 90)) if len(max_probabilities) else None,
        "maximum": float(np.max(max_probabilities)) if len(max_probabilities) else None,
    }
    return {
        "available": True,
        "distribution": distribution,
        "threshold_counts": threshold_counts,
        "focus_thresholds": {
            "0_6": next(row for row in threshold_counts if row["threshold"] == 0.6),
            "0_8": next(row for row in threshold_counts if row["threshold"] == 0.8),
        },
        "histogram": histogram,
        "top_predictions": sorted(
            predictions,
            key=lambda row: row["max_probability"],
            reverse=True,
        )[:25],
    }


def get_probability_diagnostics(experiment_id: int) -> dict:
    import joblib
    import numpy as np
    import pandas as pd

    db = SessionLocal()
    try:
        experiment = db.get(MlExperiment, experiment_id)
        if experiment is None:
            raise ValueError("Experiment was not found.")
        if experiment.status != "completed" or not experiment.model_path:
            return {"available": False, "error": "Diagnostics are available after successful training."}

        model_path = Path(experiment.model_path)
        if not model_path.exists():
            return {"available": False, "error": f"Model artifact is missing: {model_path}."}

        artifact = joblib.load(model_path)
        classifier = artifact["model"]
        feature_columns = artifact["feature_columns"]
        test_snapshot_ids = artifact.get("test_snapshot_ids", [])
        if not test_snapshot_ids:
            return {"available": False, "error": "Model artifact has no held-out test rows."}

        rows = list(
            db.execute(
                select(MlFeatureSnapshot, MlSnapshotLabel)
                .join(MlSnapshotLabel, MlSnapshotLabel.feature_snapshot_id == MlFeatureSnapshot.id)
                .where(
                    MlFeatureSnapshot.id.in_(test_snapshot_ids),
                    MlSnapshotLabel.horizon_seconds == experiment.horizon_seconds,
                    MlSnapshotLabel.is_labeled.is_(True),
                    MlSnapshotLabel.direction_label.is_not(None),
                    MlSnapshotLabel.future_return_percent.is_not(None),
                )
                .order_by(MlFeatureSnapshot.captured_at.asc(), MlFeatureSnapshot.id.asc())
            )
        )
        if not rows:
            return {"available": False, "error": "No labeled held-out rows remain for diagnostics."}

        feature_records = [
            {column: getattr(snapshot, column) for column in feature_columns}
            for snapshot, _label in rows
        ]
        features = (
            pd.DataFrame(feature_records, columns=feature_columns)
            .apply(pd.to_numeric, errors="coerce")
            .replace([np.inf, -np.inf], np.nan)
            .fillna(0)
        )
        probabilities = classifier.predict_proba(features)
        return _build_probability_diagnostics(rows, probabilities, classifier.classes_)
    except Exception as exc:
        return {
            "available": False,
            "error": str(exc)[:1000] or exc.__class__.__name__,
        }
    finally:
        db.close()


def get_training_dataset_diagnostics(experiment_id: int) -> dict:
    import joblib

    db = SessionLocal()
    try:
        experiment = db.get(MlExperiment, experiment_id)
        if experiment is None:
            raise ValueError("Experiment was not found.")
        if not experiment.model_path:
            return {"available": False, "error": "Training diagnostics are available after model artifact creation."}

        model_path = Path(experiment.model_path)
        if not model_path.exists():
            return {"available": False, "error": f"Model artifact is missing: {model_path}."}

        artifact = joblib.load(model_path)
        diagnostics = artifact.get("training_diagnostics")
        if not diagnostics:
            return {"available": False, "error": "This experiment artifact does not include training diagnostics."}

        current_latest_snapshot = db.scalar(select(func.max(MlFeatureSnapshot.captured_at)))
        return {
            "available": True,
            "diagnostics": diagnostics,
            "current_latest_snapshot_captured_at": _format_datetime(current_latest_snapshot),
        }
    except Exception as exc:
        return {
            "available": False,
            "error": str(exc)[:1000] or exc.__class__.__name__,
        }
    finally:
        db.close()


def _mark_experiment_heartbeat(experiment_id: int) -> None:
    db = SessionLocal()
    try:
        experiment = db.get(MlExperiment, experiment_id)
        if experiment is not None and experiment.status == "running":
            experiment.heartbeat_at = datetime.now(UTC)
            db.commit()
    except Exception:
        logger.exception("Failed to update ML experiment heartbeat. experiment_id=%s", experiment_id)
        db.rollback()
    finally:
        db.close()


def _experiment_heartbeat_loop(experiment_id: int, stop_event: threading.Event, interval_seconds: int) -> None:
    interval_seconds = max(1, interval_seconds)
    while not stop_event.wait(interval_seconds):
        _mark_experiment_heartbeat(experiment_id)


def fail_stale_running_experiments() -> int:
    settings = get_settings()
    now = datetime.now(UTC)
    started_cutoff = now - timedelta(minutes=max(1, settings.ml_experiment_stale_minutes))
    heartbeat_cutoff = now - timedelta(seconds=max(1, settings.ml_experiment_heartbeat_timeout_seconds))
    db = SessionLocal()
    failed_count = 0
    try:
        stale_experiments = list(
            db.scalars(
                select(MlExperiment).where(
                    MlExperiment.status == "running",
                    or_(
                        MlExperiment.started_at <= started_cutoff,
                        and_(
                            MlExperiment.heartbeat_at.is_not(None),
                            MlExperiment.heartbeat_at <= heartbeat_cutoff,
                        ),
                        and_(
                            MlExperiment.heartbeat_at.is_(None),
                            MlExperiment.started_at <= started_cutoff,
                        ),
                    ),
                )
            )
        )
        for experiment in stale_experiments:
            experiment.status = "failed"
            experiment.error_message = "Training interrupted (server restart or worker terminated)"
            experiment.completed_at = now
            failed_count += 1
        if failed_count:
            db.commit()
            logger.warning("Marked %s stale ML experiment(s) as failed.", failed_count)
        return failed_count
    except Exception:
        db.rollback()
        logger.exception("Failed to mark stale ML experiments.")
        raise
    finally:
        db.close()


def _validate_experiment_request(
    horizon_seconds: int = 30,
    model_type: str = "random_forest",
    min_rows: int = 1000,
    confidence_threshold: float = 0.8,
) -> None:
    if model_type not in SUPPORTED_MODEL_TYPES:
        raise ValueError(f"Unsupported model type: {model_type}.")
    if horizon_seconds not in {10, 30, 60}:
        raise ValueError("Horizon must be 10, 30, or 60 seconds.")
    if min_rows < 10:
        raise ValueError("Minimum rows must be at least 10.")
    if not 0 < confidence_threshold <= 1:
        raise ValueError("Confidence threshold must be greater than 0 and at most 1.")


def create_pending_direction_experiment(
    horizon_seconds: int = 30,
    model_type: str = "random_forest",
    min_rows: int = 1000,
    confidence_threshold: float = 0.8,
    title: str | None = None,
) -> MlExperiment:
    _validate_experiment_request(horizon_seconds, model_type, min_rows, confidence_threshold)
    db = SessionLocal()
    try:
        experiment = MlExperiment(
            title=(title or f"Direction experiment {horizon_seconds}s").strip()[:160],
            status="pending",
            model_type=model_type,
            target_type="direction_label",
            horizon_seconds=horizon_seconds,
            confidence_threshold=_to_decimal(confidence_threshold),
            min_rows=min_rows,
        )
        db.add(experiment)
        db.commit()
        db.refresh(experiment)
        db.expunge(experiment)
        return experiment
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def run_direction_experiment_training(experiment_id: int) -> dict[str, object]:
    db = SessionLocal()
    experiment = db.get(MlExperiment, experiment_id)
    if experiment is None:
        logger.error("ML experiment background training skipped: experiment_id=%s was not found.", experiment_id)
        db.close()
        return {"success": False, "message": "Experiment was not found.", "experiment": None}
    horizon_seconds = experiment.horizon_seconds
    model_type = experiment.model_type
    min_rows = experiment.min_rows
    settings = get_settings()
    heartbeat_stop_event = threading.Event()
    heartbeat_thread: threading.Thread | None = None

    try:
        import joblib
        import numpy as np
        import pandas as pd
        from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
        from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

        experiment.status = "running"
        experiment.started_at = datetime.now(UTC)
        experiment.heartbeat_at = experiment.started_at
        db.commit()
        heartbeat_thread = threading.Thread(
            target=_experiment_heartbeat_loop,
            args=(
                experiment_id,
                heartbeat_stop_event,
                settings.ml_experiment_heartbeat_interval_seconds,
            ),
            daemon=True,
        )
        heartbeat_thread.start()

        training_diagnostics = _build_training_dataset_diagnostics(db, horizon_seconds)
        logger.info(
            "ML experiment training dataset diagnostics: "
            "horizon=%s total_feature_snapshots=%s total_labels_for_horizon=%s "
            "labeled_labels_for_horizon=%s labels_joined_to_feature_snapshots=%s "
            "labeled_labels_joined_to_feature_snapshots=%s rows_after_data_quality=%s "
            "distinct_features_after_data_quality=%s duplicate_label_rows_after_data_quality=%s "
            "training_min_captured_at=%s training_max_captured_at=%s latest_snapshot_captured_at=%s",
            horizon_seconds,
            training_diagnostics["total_feature_snapshots"],
            training_diagnostics["total_labels_for_selected_horizon"],
            training_diagnostics["labeled_labels_for_selected_horizon"],
            training_diagnostics["labels_joined_to_feature_snapshots"],
            training_diagnostics["labeled_labels_joined_to_feature_snapshots"],
            training_diagnostics["rows_after_data_quality_filter"],
            training_diagnostics["distinct_feature_snapshots_after_data_quality_filter"],
            training_diagnostics["duplicate_label_rows_after_data_quality_filter"],
            training_diagnostics["training_min_captured_at"],
            training_diagnostics["training_max_captured_at"],
            training_diagnostics["latest_snapshot_captured_at_in_database"],
        )

        rows = list(
            db.execute(
                select(MlFeatureSnapshot, MlSnapshotLabel)
                .join(MlSnapshotLabel, MlSnapshotLabel.feature_snapshot_id == MlFeatureSnapshot.id)
                .where(
                    MlSnapshotLabel.horizon_seconds == horizon_seconds,
                    MlSnapshotLabel.is_labeled.is_(True),
                    MlSnapshotLabel.direction_label.is_not(None),
                    MlSnapshotLabel.future_return_percent.is_not(None),
                    MlFeatureSnapshot.data_quality_score >= MIN_EXPERIMENT_DATA_QUALITY_SCORE,
                )
                .order_by(MlFeatureSnapshot.captured_at.asc(), MlFeatureSnapshot.id.asc())
            )
        )
        if len(rows) < min_rows:
            raise ValueError(
                f"Need at least {min_rows} labeled rows with data quality >= 60 "
                f"for horizon {horizon_seconds}s; found {len(rows)}."
            )

        records = []
        for snapshot, label in rows:
            record = {column: getattr(snapshot, column) for column in FEATURE_COLUMNS}
            record.update(
                {
                    "snapshot_id": snapshot.id,
                    "captured_at": snapshot.captured_at,
                    "direction_label": label.direction_label,
                }
            )
            records.append(record)

        frame = pd.DataFrame(records)
        training_diagnostics = _build_training_dataset_diagnostics(
            db,
            horizon_seconds,
            final_dataframe_rows=len(frame),
        )
        logger.info(
            "ML experiment final dataframe diagnostics: horizon=%s final_dataframe_rows=%s "
            "training_min_captured_at=%s training_max_captured_at=%s latest_snapshot_captured_at=%s",
            horizon_seconds,
            training_diagnostics["final_dataframe_rows"],
            training_diagnostics["training_min_captured_at"],
            training_diagnostics["training_max_captured_at"],
            training_diagnostics["latest_snapshot_captured_at_in_database"],
        )
        feature_frame = (
            frame[FEATURE_COLUMNS]
            .apply(pd.to_numeric, errors="coerce")
            .replace([np.inf, -np.inf], np.nan)
            .fillna(0)
        )
        split_index = int(len(frame) * 0.7)
        if split_index <= 0 or split_index >= len(frame):
            raise ValueError("Not enough rows to create a chronological 70/30 train/test split.")

        x_train = feature_frame.iloc[:split_index]
        x_test = feature_frame.iloc[split_index:]
        y_train = frame["direction_label"].iloc[:split_index]
        y_test = frame["direction_label"].iloc[split_index:]
        if y_train.nunique() < 2:
            raise ValueError("Training portion must contain at least two direction classes.")

        if model_type == "random_forest":
            classifier = RandomForestClassifier(
                n_estimators=300,
                random_state=42,
                n_jobs=-1,
                class_weight="balanced",
                min_samples_leaf=2,
            )
        else:
            classifier = GradientBoostingClassifier(random_state=42)

        classifier.fit(x_train, y_train)
        predictions = classifier.predict(x_test)
        accuracy = float(accuracy_score(y_test, predictions))
        report = classification_report(
            y_test,
            predictions,
            labels=CLASS_LABELS,
            output_dict=True,
            zero_division=0,
        )
        matrix = confusion_matrix(y_test, predictions, labels=CLASS_LABELS).tolist()
        importances = sorted(
            (
                {"feature": feature, "importance": float(importance)}
                for feature, importance in zip(FEATURE_COLUMNS, classifier.feature_importances_, strict=True)
            ),
            key=lambda item: item["importance"],
            reverse=True,
        )

        model_dir = Path("storage/models/experiments")
        model_dir.mkdir(parents=True, exist_ok=True)
        model_path = model_dir / f"{experiment.public_id}.joblib"
        artifact = {
            "model": classifier,
            "feature_columns": FEATURE_COLUMNS,
            "classes": list(classifier.classes_),
            "horizon_seconds": horizon_seconds,
            "train_rows_count": len(x_train),
            "test_rows_count": len(x_test),
            "test_snapshot_ids": [int(value) for value in frame["snapshot_id"].iloc[split_index:].tolist()],
            "split_captured_at": frame["captured_at"].iloc[split_index].isoformat(),
            "training_diagnostics": training_diagnostics,
        }
        joblib.dump(artifact, model_path)

        experiment.status = "completed"
        experiment.train_rows_count = len(x_train)
        experiment.test_rows_count = len(x_test)
        experiment.accuracy = _to_decimal(accuracy)
        experiment.confusion_matrix_json = matrix
        experiment.feature_importance_json = importances
        experiment.classification_report_json = report
        experiment.model_path = str(model_path)
        experiment.error_message = None
        experiment.completed_at = datetime.now(UTC)
        _set_class_metrics(experiment, report)
        db.commit()
        db.refresh(experiment)
        return {
            "success": True,
            "message": f"Experiment trained on {len(x_train)} rows and tested on {len(x_test)} held-out rows.",
            "experiment": experiment,
        }
    except Exception as exc:
        db.rollback()
        experiment = db.get(MlExperiment, experiment.id)
        experiment.status = "failed"
        experiment.error_message = str(exc)[:4000] or exc.__class__.__name__
        experiment.completed_at = datetime.now(UTC)
        db.commit()
        db.refresh(experiment)
        return {"success": False, "message": experiment.error_message, "experiment": experiment}
    finally:
        heartbeat_stop_event.set()
        if heartbeat_thread and heartbeat_thread.is_alive():
            heartbeat_thread.join(timeout=5)
        db.close()


def train_direction_experiment(
    horizon_seconds: int = 30,
    model_type: str = "random_forest",
    min_rows: int = 1000,
    confidence_threshold: float = 0.8,
    title: str | None = None,
) -> dict[str, object]:
    experiment = create_pending_direction_experiment(
        title=title,
        horizon_seconds=horizon_seconds,
        model_type=model_type,
        min_rows=min_rows,
        confidence_threshold=confidence_threshold,
    )
    return run_direction_experiment_training(experiment.id)
