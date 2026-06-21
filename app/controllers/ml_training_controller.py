from urllib.parse import urlencode

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.core.ml_training_runner import start_ml_training_runner, stop_ml_training_runner
from app.services.ml_labeling_service import process_pending_labels
from app.services.ml_stats_service import get_ml_training_stats
from app.services.ml_training_service import train_basic_direction_model


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _redirect_with_message(status: str, message: str) -> RedirectResponse:
    return RedirectResponse(url=f"/ml-training?{urlencode({'status': status, 'message': message})}", status_code=303)


@router.get("/ml-training")
def ml_training_dashboard(
    request: Request,
    status: str | None = Query(None),
    message: str | None = Query(None),
):
    return templates.TemplateResponse(
        "ml_training/index.html",
        {"request": request, "stats": get_ml_training_stats(), "status": status, "message": message},
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


@router.post("/ml-training/train-basic-model")
def train_basic_model(horizon_seconds: int = Form(30)):
    result = train_basic_direction_model(horizon_seconds)
    return _redirect_with_message("success" if result["success"] else "danger", str(result["message"]))
