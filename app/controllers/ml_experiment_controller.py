import uuid
import logging
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import SessionLocal
from app.models.ml_experiment import MlExperiment
from app.services.ml_experiment_service import (
    get_dataset_eligibility_diagnostics,
    get_experiment_dashboard_data,
    get_probability_diagnostics,
    train_direction_experiment,
)
from app.services.ml_shadow_backtest_service import backtest_edge_status, run_shadow_backtest


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger(__name__)


def _format_metric(value, places: int = 4) -> str:
    if value is None:
        return "-"
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return str(value)
    if number == 0:
        return "0"
    return f"{number:.{places}f}".rstrip("0").rstrip(".")


templates.env.filters["metric"] = _format_metric


def _redirect(url: str, status: str, message: str) -> RedirectResponse:
    return RedirectResponse(url=f"{url}?{urlencode({'status': status, 'message': message})}", status_code=303)


@router.get("/ml-experiments")
def ml_experiments_dashboard(
    request: Request,
    status: str | None = Query(None),
    message: str | None = Query(None),
):
    return templates.TemplateResponse(
        "ml_experiments/index.html",
        {
            "request": request,
            "dashboard": get_experiment_dashboard_data(),
            "eligibility": get_dataset_eligibility_diagnostics(),
            "status": status,
            "message": message,
        },
    )


@router.post("/ml-experiments/train")
def train_experiment(
    title: str = Form(...),
    horizon_seconds: int = Form(30),
    model_type: str = Form("random_forest"),
    min_rows: int = Form(1000),
    confidence_threshold: float = Form(0.8),
):
    try:
        result = train_direction_experiment(
            title=title,
            horizon_seconds=horizon_seconds,
            model_type=model_type,
            min_rows=min_rows,
            confidence_threshold=confidence_threshold,
        )
    except Exception as exc:
        logger.exception("ML experiment training request failed before an experiment could complete.")
        return _redirect("/ml-experiments", "danger", f"Experiment could not start: {exc}")
    experiment = result["experiment"]
    if result["success"]:
        return _redirect(
            f"/ml-experiments/{experiment.public_id}",
            "success",
            str(result["message"]),
        )
    return _redirect("/ml-experiments", "danger", str(result["message"]))


def _load_experiment(public_id: str) -> MlExperiment:
    try:
        parsed_public_id = uuid.UUID(public_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Experiment not found.") from exc

    db = SessionLocal()
    try:
        experiment = db.scalar(
            select(MlExperiment)
            .options(selectinload(MlExperiment.shadow_backtests))
            .where(MlExperiment.public_id == parsed_public_id)
        )
        if experiment is None:
            raise HTTPException(status_code=404, detail="Experiment not found.")
        db.expunge_all()
        return experiment
    finally:
        db.close()


@router.get("/ml-experiments/{public_id}")
def experiment_details(
    public_id: str,
    request: Request,
    status: str | None = Query(None),
    message: str | None = Query(None),
):
    experiment = _load_experiment(public_id)
    probability_diagnostics = get_probability_diagnostics(experiment.id)
    return templates.TemplateResponse(
        "ml_experiments/details.html",
        {
            "request": request,
            "experiment": experiment,
            "probability_diagnostics": probability_diagnostics,
            "backtest_rows": [
                {"backtest": backtest, "edge": backtest_edge_status(backtest)}
                for backtest in experiment.shadow_backtests
            ],
            "status": status,
            "message": message,
        },
    )


@router.post("/ml-experiments/{public_id}/run-backtest")
def run_experiment_backtest(
    public_id: str,
    confidence_threshold: float = Form(0.8),
    fees_percent: float = Form(0.1),
    slippage_percent: float = Form(0.05),
):
    experiment = _load_experiment(public_id)
    try:
        backtest = run_shadow_backtest(
            experiment.id,
            confidence_threshold=confidence_threshold,
            fees_percent=fees_percent,
            slippage_percent=slippage_percent,
        )
    except Exception as exc:
        return _redirect(
            f"/ml-experiments/{experiment.public_id}",
            "danger",
            f"Shadow backtest failed: {exc}",
        )
    return _redirect(
        f"/ml-experiments/{experiment.public_id}",
        "success",
        f"Shadow backtest completed with {backtest.total_signals} accepted signals.",
    )
