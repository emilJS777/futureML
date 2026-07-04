import logging
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.core.ml_training_runner import capture_once_debug, start_ml_training_runner, stop_ml_training_runner
from app.services.ml_dataset_cleanup_service import delete_ml_dataset
from app.services.ml_labeling_service import (
    backfill_advanced_labels,
    backfill_pending_labels_in_batches,
    process_pending_labels,
)
from app.services.ml_stats_service import get_ml_training_stats
from app.services.ml_training_service import train_basic_direction_model


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger(__name__)


def _format_feature_value(value, places: int = 6) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, int):
        return str(value)
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return str(value)
    if number == 0:
        return "0"
    formatted = f"{number:.{places}f}".rstrip("0").rstrip(".")
    return formatted or "0"


templates.env.filters["feature_value"] = _format_feature_value


def _redirect_with_message(status: str, message: str) -> RedirectResponse:
    return RedirectResponse(url=f"/ml-training?{urlencode({'status': status, 'message': message})}", status_code=303)


@router.get("/ml-training")
def ml_training_dashboard(
    request: Request,
    status: str | None = Query(None),
    message: str | None = Query(None),
    snapshots_page: int = Query(1, ge=1),
    snapshots_page_size: int = Query(10, ge=1, le=100),
):
    return templates.TemplateResponse(
        "ml_training/index.html",
        {
            "request": request,
            "stats": get_ml_training_stats(snapshots_page, snapshots_page_size),
            "status": status,
            "message": message,
        },
    )


@router.post("/ml-training/start")
async def start_ml_training(interval_seconds: int = Form(5)):
    session = await start_ml_training_runner(interval_seconds)
    return _redirect_with_message("success", f"Training session started with {session.interval_seconds}s interval.")


@router.post("/ml-training/stop")
async def stop_ml_training():
    session = await stop_ml_training_runner()
    if session is None:
        return _redirect_with_message("warning", "No running training session was found.")
    return _redirect_with_message("success", "Training session stopped.")


@router.post("/ml-training/process-labels")
def process_labels():
    result = process_pending_labels()
    return _redirect_with_message("success", f"Processed {result['processed']} labels; skipped {result['skipped']}.")


@router.post("/ml-training/backfill-labels")
def backfill_labels():
    result = backfill_advanced_labels()
    return _redirect_with_message(
        "success",
        f"Backfilled advanced labels for {result['updated']} rows; skipped {result['skipped']}.",
    )


@router.post("/ml-training/backfill-pending-labels")
def backfill_pending_labels(
    batch_size: int = Form(1000),
    max_batches: int = Form(10),
):
    result = backfill_pending_labels_in_batches(batch_size=batch_size, max_batches=max_batches)
    skip_breakdown = ", ".join(
        f"{reason}={count}" for reason, count in result["skip_reasons"].items() if count
    ) or "none"
    return _redirect_with_message(
        "success" if result["processed"] else "warning",
        "Pending label backfill: "
        f"processed {result['processed']}, skipped {result['skipped']}, "
        f"batches {result['batches_run']}, remaining pending {result['remaining_pending']}, "
        f"eligible now {result['remaining_eligible_pending']}. "
        f"Skip reasons: {skip_breakdown}. "
        f"Safety {result['safety_seconds']}s, fallback tolerance {result['future_lookup_tolerance_seconds']}s.",
    )


@router.post("/ml-training/delete-dataset")
async def delete_dataset(delete_models: bool = Form(False)):
    try:
        await stop_ml_training_runner()
        result = delete_ml_dataset(delete_models=delete_models)
    except Exception as exc:
        logger.exception("Failed to delete ML dataset")
        return _redirect_with_message("danger", f"Failed to delete ML dataset: {exc}")

    message = (
        "Deleted ML dataset: "
        f"{result['deleted_feature_snapshots']} feature snapshots, "
        f"{result['deleted_labels']} labels, "
        f"{result['deleted_recent_trades']} recent trades snapshots, "
        f"{result['deleted_micro_candles']} micro candles."
    )
    if result["stopped_sessions"]:
        message = f"Stopped {result['stopped_sessions']} running training session(s). {message}"
    if delete_models:
        message = (
            f"{message} Deleted {result['deleted_models']} trained model rows "
            f"and {result['deleted_model_files']} model file(s)."
        )
    return _redirect_with_message("success", message)


@router.post("/ml-training/capture-once")
async def capture_once():
    result = await capture_once_debug()
    message = (
        f"Capture once: active pairs {result['total_active_pairs_found']}, "
        f"attempted {len(result['attempted_exchanges'])}, "
        f"success {result['success_count']}, failed {result['failed_count']}, "
        f"created snapshots {result['created_snapshots_count']}."
    )
    if result["error_messages"]:
        message = f"{message} Errors: {'; '.join(result['error_messages'])}"
    return _redirect_with_message("success" if result["success_count"] else "danger", message)


@router.post("/ml-training/train-basic-model")
def train_basic_model(horizon_seconds: int = Form(30)):
    result = train_basic_direction_model(horizon_seconds)
    return _redirect_with_message("success" if result["success"] else "danger", str(result["message"]))
