from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.models.ml_experiment import MlExperiment
from app.models.ml_feature_snapshot import MlFeatureSnapshot
from app.models.ml_snapshot_label import MlSnapshotLabel
from app.services.ml_training_service import FEATURE_COLUMNS


CLASS_LABELS = ["long", "short", "flat"]
SUPPORTED_MODEL_TYPES = {"random_forest", "gradient_boosting"}


def _to_decimal(value: float | None) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


def _set_class_metrics(experiment: MlExperiment, report: dict) -> None:
    for label in CLASS_LABELS:
        metrics = report.get(label, {})
        setattr(experiment, f"precision_{label}", _to_decimal(metrics.get("precision")))
        setattr(experiment, f"recall_{label}", _to_decimal(metrics.get("recall")))
        setattr(experiment, f"f1_{label}", _to_decimal(metrics.get("f1-score")))


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
                    MlFeatureSnapshot.data_quality_score >= 60,
                )
            )
            or 0
            for horizon in (10, 30, 60)
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


def train_direction_experiment(
    horizon_seconds: int = 30,
    model_type: str = "random_forest",
    min_rows: int = 1000,
    confidence_threshold: float = 0.8,
    title: str | None = None,
) -> dict[str, object]:
    if model_type not in SUPPORTED_MODEL_TYPES:
        raise ValueError(f"Unsupported model type: {model_type}.")
    if horizon_seconds not in {10, 30, 60}:
        raise ValueError("Horizon must be 10, 30, or 60 seconds.")
    if min_rows < 10:
        raise ValueError("Minimum rows must be at least 10.")
    if not 0 < confidence_threshold <= 1:
        raise ValueError("Confidence threshold must be greater than 0 and at most 1.")

    db = SessionLocal()
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

    try:
        import joblib
        import numpy as np
        import pandas as pd
        from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
        from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

        experiment.status = "running"
        experiment.started_at = datetime.now(UTC)
        db.commit()

        rows = list(
            db.execute(
                select(MlFeatureSnapshot, MlSnapshotLabel)
                .join(MlSnapshotLabel, MlSnapshotLabel.feature_snapshot_id == MlFeatureSnapshot.id)
                .where(
                    MlSnapshotLabel.horizon_seconds == horizon_seconds,
                    MlSnapshotLabel.is_labeled.is_(True),
                    MlSnapshotLabel.direction_label.is_not(None),
                    MlFeatureSnapshot.data_quality_score >= 60,
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
        db.close()
