from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.ml_feature_snapshot import MlFeatureSnapshot
from app.models.ml_model import MlModel
from app.models.ml_snapshot_label import MlSnapshotLabel


FEATURE_COLUMNS = [
    "best_bid",
    "best_ask",
    "spread",
    "spread_percent",
    "mid_price",
    "last_price",
    "mark_price",
    "index_price",
    "funding_rate",
    "open_interest",
    "volume_24h",
    "quote_volume_24h",
    "price_change_percent_24h",
    "bid_depth_5",
    "ask_depth_5",
    "bid_depth_10",
    "ask_depth_10",
    "bid_depth_20",
    "ask_depth_20",
    "order_book_imbalance_5",
    "order_book_imbalance_10",
    "order_book_imbalance_20",
    "top_bid_size",
    "top_ask_size",
    "bid_wall_score",
    "ask_wall_score",
    "buy_volume",
    "sell_volume",
    "buy_sell_delta",
    "buy_sell_ratio",
    "avg_trade_size",
    "large_trade_count",
    "largest_trade_size",
    "bid_depth_5_delta",
    "ask_depth_5_delta",
    "imbalance_5_delta",
    "bid_depth_10_delta",
    "ask_depth_10_delta",
    "imbalance_10_delta",
    "spread_delta",
    "mid_price_delta",
    "wall_shift_score",
    "candle_return_1",
    "candle_return_3",
    "candle_volume_1",
    "candle_volume_avg_5",
    "candle_momentum_5",
    "funding_rate_delta",
    "funding_rate_abs",
    "funding_pressure_score",
    "capture_latency_ms",
    "data_quality_score",
    "missing_fields_count",
    "cross_exchange_mid_avg",
    "cross_exchange_mid_median",
    "cross_exchange_price_deviation_percent",
    "cross_exchange_spread_percent",
]

TARGET_COLUMNS = [
    "direction_label",
    "long_tp_hit_0_3",
    "short_tp_hit_0_3",
    "expected_long_return_percent",
    "expected_short_return_percent",
]


def _to_decimal(value: float | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _failed_model(db, horizon_seconds: int, rows_count: int, message: str) -> MlModel:
    model = MlModel(
        title=f"Failed direction model {horizon_seconds}s",
        status="failed",
        model_type="RandomForestClassifier",
        target_horizon_seconds=horizon_seconds,
        train_rows_count=rows_count,
        feature_columns_json=FEATURE_COLUMNS,
        metrics_json={"error": message},
        trained_at=datetime.now(UTC),
    )
    db.add(model)
    db.commit()
    db.refresh(model)
    return model


def train_basic_direction_model(horizon_seconds: int = 30) -> dict[str, object]:
    import joblib
    import pandas as pd
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import accuracy_score, precision_score
    from sklearn.model_selection import train_test_split

    db = SessionLocal()
    try:
        rows = list(
            db.execute(
                select(MlFeatureSnapshot, MlSnapshotLabel)
                .join(MlSnapshotLabel, MlSnapshotLabel.feature_snapshot_id == MlFeatureSnapshot.id)
                .where(
                    MlSnapshotLabel.horizon_seconds == horizon_seconds,
                    MlSnapshotLabel.is_labeled.is_(True),
                    MlSnapshotLabel.direction_label.is_not(None),
                )
            )
        )
        if len(rows) < 1000:
            message = f"Need at least 1000 labeled rows for horizon {horizon_seconds}s; found {len(rows)}."
            model = _failed_model(db, horizon_seconds, len(rows), message)
            return {"success": False, "message": message, "model": model}

        records = []
        for snapshot, label in rows:
            record = {column: getattr(snapshot, column) for column in FEATURE_COLUMNS}
            record["direction_label"] = label.direction_label
            records.append(record)

        df = pd.DataFrame(records)
        df = df.dropna(subset=["direction_label"])
        if len(df) < 1000:
            message = f"Need at least 1000 usable labeled rows; found {len(df)} after dropping null targets."
            model = _failed_model(db, horizon_seconds, len(df), message)
            return {"success": False, "message": message, "model": model}

        x = df[FEATURE_COLUMNS].apply(pd.to_numeric, errors="coerce").fillna(0)
        y = df["direction_label"]
        x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=0.2, random_state=42, stratify=y)
        classifier = RandomForestClassifier(n_estimators=200, random_state=42, n_jobs=-1, class_weight="balanced")
        classifier.fit(x_train, y_train)
        predictions = classifier.predict(x_test)

        accuracy = accuracy_score(y_test, predictions)
        precision = precision_score(y_test, predictions, labels=["long", "short", "flat"], average=None, zero_division=0)
        metrics = {
            "accuracy": accuracy,
            "precision_long": precision[0],
            "precision_short": precision[1],
            "precision_flat": precision[2],
            "classes": list(classifier.classes_),
        }

        model = MlModel(
            title=f"Direction model {horizon_seconds}s",
            status="trained",
            model_type="RandomForestClassifier",
            target_horizon_seconds=horizon_seconds,
            train_rows_count=len(df),
            accuracy=_to_decimal(accuracy),
            precision_long=_to_decimal(precision[0]),
            precision_short=_to_decimal(precision[1]),
            precision_flat=_to_decimal(precision[2]),
            feature_columns_json=FEATURE_COLUMNS,
            metrics_json=metrics,
            trained_at=datetime.now(UTC),
        )
        db.add(model)
        db.flush()

        model_dir = Path("storage/models")
        model_dir.mkdir(parents=True, exist_ok=True)
        model_path = model_dir / f"{model.public_id}.joblib"
        joblib.dump({"model": classifier, "feature_columns": FEATURE_COLUMNS, "metrics": metrics}, model_path)
        model.model_path = str(model_path)
        db.commit()
        db.refresh(model)
        return {"success": True, "message": f"Trained model on {len(df)} labeled rows.", "model": model}
    except Exception as exc:
        db.rollback()
        model = _failed_model(db, horizon_seconds, 0, str(exc)[:1000] or exc.__class__.__name__)
        return {"success": False, "message": str(exc)[:1000] or exc.__class__.__name__, "model": model}
    finally:
        db.close()
