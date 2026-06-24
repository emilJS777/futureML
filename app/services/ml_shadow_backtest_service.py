from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.ml_experiment import MlExperiment
from app.models.ml_feature_snapshot import MlFeatureSnapshot
from app.models.ml_shadow_backtest import MlShadowBacktest
from app.models.ml_snapshot_label import MlSnapshotLabel


def _to_decimal(value: float | None) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


def backtest_edge_status(backtest: MlShadowBacktest) -> tuple[str, str]:
    if backtest.total_signals < 30:
        return "Weak / Insufficient", "warning"
    if backtest.net_expectancy_percent is not None and backtest.net_expectancy_percent > 0:
        return "Positive Edge", "success"
    return "Negative Edge", "danger"


def run_shadow_backtest(
    experiment_id: int,
    confidence_threshold: float = 0.8,
    fees_percent: float = 0.1,
    slippage_percent: float = 0.05,
) -> MlShadowBacktest:
    import joblib
    import numpy as np
    import pandas as pd

    if not 0 < confidence_threshold <= 1:
        raise ValueError("Confidence threshold must be greater than 0 and at most 1.")
    if fees_percent < 0 or slippage_percent < 0:
        raise ValueError("Fees and slippage cannot be negative.")

    db = SessionLocal()
    try:
        experiment = db.get(MlExperiment, experiment_id)
        if experiment is None:
            raise ValueError("Experiment was not found.")
        if experiment.status != "completed" or not experiment.model_path:
            raise ValueError("Experiment must be completed before running a shadow backtest.")
        model_path = Path(experiment.model_path)
        if not model_path.exists():
            raise ValueError(f"Model artifact is missing: {model_path}.")

        artifact = joblib.load(model_path)
        classifier = artifact["model"]
        feature_columns = artifact["feature_columns"]
        test_snapshot_ids = artifact.get("test_snapshot_ids", [])
        if not test_snapshot_ids:
            raise ValueError("Model artifact does not contain held-out test rows.")

        rows = list(
            db.execute(
                select(MlFeatureSnapshot, MlSnapshotLabel)
                .join(MlSnapshotLabel, MlSnapshotLabel.feature_snapshot_id == MlFeatureSnapshot.id)
                .where(
                    MlFeatureSnapshot.id.in_(test_snapshot_ids),
                    MlSnapshotLabel.horizon_seconds == experiment.horizon_seconds,
                    MlSnapshotLabel.is_labeled.is_(True),
                    MlSnapshotLabel.future_return_percent.is_not(None),
                )
                .order_by(MlFeatureSnapshot.captured_at.asc(), MlFeatureSnapshot.id.asc())
            )
        )
        if not rows:
            raise ValueError("No labeled held-out rows remain for this experiment.")

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
        predicted_classes = classifier.classes_

        fee_drag = fees_percent + slippage_percent
        equity = 0.0
        equity_curve = [{"index": 0, "equity_percent": 0.0}]
        peak = 0.0
        max_drawdown = 0.0
        results = []
        long_signals = 0
        short_signals = 0
        flat_skipped = 0
        raw_returns = []
        net_returns = []

        for index, ((snapshot, label), row_probabilities) in enumerate(zip(rows, probabilities, strict=True), start=1):
            best_index = int(np.argmax(row_probabilities))
            confidence = float(row_probabilities[best_index])
            prediction = str(predicted_classes[best_index])
            if confidence < confidence_threshold or prediction == "flat":
                flat_skipped += 1
                continue

            future_return = float(label.future_return_percent)
            if prediction == "long":
                raw_return = future_return
                long_signals += 1
            elif prediction == "short":
                raw_return = -future_return
                short_signals += 1
            else:
                flat_skipped += 1
                continue

            net_return = raw_return - fee_drag
            raw_returns.append(raw_return)
            net_returns.append(net_return)
            equity += net_return
            peak = max(peak, equity)
            max_drawdown = max(max_drawdown, peak - equity)
            equity_curve.append({"index": len(net_returns), "equity_percent": equity})
            results.append(
                {
                    "snapshot_public_id": str(snapshot.public_id),
                    "captured_at": snapshot.captured_at.isoformat(),
                    "exchange_code": snapshot.exchange_code,
                    "symbol": snapshot.symbol,
                    "prediction": prediction,
                    "confidence": confidence,
                    "raw_return_percent": raw_return,
                    "net_return_percent": net_return,
                }
            )

        total_signals = len(net_returns)
        wins = [value for value in net_returns if value > 0]
        losses = [value for value in net_returns if value <= 0]
        gross_profit = sum(wins)
        gross_loss = sum(losses)
        profit_factor = gross_profit / abs(gross_loss) if gross_loss < 0 else None

        backtest = MlShadowBacktest(
            ml_experiment_id=experiment.id,
            horizon_seconds=experiment.horizon_seconds,
            confidence_threshold=_to_decimal(confidence_threshold),
            total_signals=total_signals,
            long_signals=long_signals,
            short_signals=short_signals,
            flat_skipped=flat_skipped,
            win_count=len(wins),
            loss_count=len(losses),
            win_rate=_to_decimal((len(wins) / total_signals) * 100 if total_signals else None),
            avg_win_percent=_to_decimal(sum(wins) / len(wins) if wins else None),
            avg_loss_percent=_to_decimal(sum(losses) / len(losses) if losses else None),
            gross_profit_percent=_to_decimal(gross_profit),
            gross_loss_percent=_to_decimal(gross_loss),
            expectancy_percent=_to_decimal(sum(raw_returns) / total_signals if total_signals else None),
            max_drawdown_percent=_to_decimal(max_drawdown if total_signals else None),
            profit_factor=_to_decimal(profit_factor),
            fees_percent=_to_decimal(fees_percent),
            slippage_percent=_to_decimal(slippage_percent),
            net_expectancy_percent=_to_decimal(sum(net_returns) / total_signals if total_signals else None),
            equity_curve_json=equity_curve,
            results_json=results[-100:],
        )
        db.add(backtest)
        db.commit()
        db.refresh(backtest)
        return backtest
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
