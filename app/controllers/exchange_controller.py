import uuid
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.exchange_credential import ExchangeCredentialCreate, ExchangeCredentialUpdate
from app.services.ccxt_service import test_exchange_connection
from app.services.exchange_service import (
    EXCHANGE_PRESETS,
    create_credential,
    delete_credential,
    get_credential,
    list_credentials,
    masked_api_key,
    update_credential,
)
from app.services.market_data_service import capture_market_data_for_exchange
from app.services.market_discovery_service import (
    get_selected_market,
    list_exchange_markets,
    select_market_for_data_collection,
    sync_exchange_futures_markets,
)


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


templates.env.filters["masked_api_key"] = masked_api_key


def _preset_context() -> list[dict]:
    return [preset.model_dump() for preset in EXCHANGE_PRESETS]


def _bool_form(value: str | None) -> bool:
    return value == "on"


def _form_error(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return "; ".join(error["msg"] for error in exc.errors())
    return str(exc)


def _get_or_404(db: Session, public_id: uuid.UUID):
    credential = get_credential(db, public_id)
    if credential is None:
        raise HTTPException(status_code=404, detail="Exchange credential not found")
    return credential


def _redirect_with_message(path: str, status: str, message: str) -> RedirectResponse:
    return RedirectResponse(url=f"{path}?{urlencode({'status': status, 'message': message})}", status_code=303)


@router.get("/exchanges")
def index(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        "exchanges/index.html",
        {"request": request, "credentials": list_credentials(db)},
    )


@router.get("/exchanges/create")
def create_form(request: Request):
    return templates.TemplateResponse(
        "exchanges/create.html",
        {"request": request, "presets": EXCHANGE_PRESETS, "presets_json": _preset_context(), "error": None, "form": {}},
    )


@router.post("/exchanges/create")
def create_submit(
    request: Request,
    db: Session = Depends(get_db),
    title: str = Form(...),
    exchange_code: str = Form(...),
    icon_path: str = Form(""),
    sort_index: int = Form(0),
    api_key: str = Form(...),
    api_secret: str = Form(...),
    password: str = Form(""),
    is_active: str | None = Form(None),
    is_futures_enabled: str | None = Form(None),
):
    form = dict(
        title=title,
        exchange_code=exchange_code,
        icon_path=icon_path or None,
        sort_index=sort_index,
        api_key=api_key,
        api_secret=api_secret,
        password=password or None,
        is_active=_bool_form(is_active),
        is_futures_enabled=_bool_form(is_futures_enabled),
    )
    try:
        payload = ExchangeCredentialCreate(**form)
        credential = create_credential(db, payload)
        return RedirectResponse(url=f"/exchanges/{credential.public_id}", status_code=303)
    except Exception as exc:
        return templates.TemplateResponse(
            "exchanges/create.html",
            {
                "request": request,
                "presets": EXCHANGE_PRESETS,
                "presets_json": _preset_context(),
                "error": _form_error(exc),
                "form": form,
            },
            status_code=400,
        )


@router.get("/exchanges/{public_id}")
def details(
    public_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    status: str | None = Query(None),
    message: str | None = Query(None),
):
    credential = _get_or_404(db, public_id)
    return templates.TemplateResponse(
        "exchanges/details.html",
        {
            "request": request,
            "credential": credential,
            "markets": list_exchange_markets(db, credential),
            "selected_market": get_selected_market(db, credential),
            "status": status,
            "message": message,
        },
    )


@router.get("/exchanges/{public_id}/edit")
def edit_form(public_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    credential = _get_or_404(db, public_id)
    return templates.TemplateResponse(
        "exchanges/edit.html",
        {
            "request": request,
            "credential": credential,
            "presets": EXCHANGE_PRESETS,
            "presets_json": _preset_context(),
            "error": None,
        },
    )


@router.post("/exchanges/{public_id}/edit")
def edit_submit(
    public_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    title: str = Form(...),
    exchange_code: str = Form(...),
    icon_path: str = Form(""),
    sort_index: int = Form(0),
    api_key: str = Form(""),
    api_secret: str = Form(""),
    password: str = Form(""),
    is_active: str | None = Form(None),
    is_futures_enabled: str | None = Form(None),
):
    credential = _get_or_404(db, public_id)
    form = dict(
        title=title,
        exchange_code=exchange_code,
        icon_path=icon_path or None,
        sort_index=sort_index,
        api_key=api_key or None,
        api_secret=api_secret or None,
        password=password or None,
        is_active=_bool_form(is_active),
        is_futures_enabled=_bool_form(is_futures_enabled),
    )
    try:
        payload = ExchangeCredentialUpdate(**form)
        update_credential(db, credential, payload)
        return RedirectResponse(url=f"/exchanges/{public_id}", status_code=303)
    except Exception as exc:
        return templates.TemplateResponse(
            "exchanges/edit.html",
            {
                "request": request,
                "credential": credential,
                "presets": EXCHANGE_PRESETS,
                "presets_json": _preset_context(),
                "error": _form_error(exc),
                "form": form,
            },
            status_code=400,
        )


@router.post("/exchanges/{public_id}/test")
def test_connection(public_id: uuid.UUID, db: Session = Depends(get_db)):
    credential = _get_or_404(db, public_id)
    test_exchange_connection(db, credential)
    return RedirectResponse(url=f"/exchanges/{public_id}", status_code=303)


@router.post("/exchanges/{public_id}/sync-futures-markets")
def sync_futures_markets(public_id: uuid.UUID, db: Session = Depends(get_db)):
    credential = _get_or_404(db, public_id)
    result = sync_exchange_futures_markets(db, credential)
    return _redirect_with_message(
        f"/exchanges/{public_id}",
        "success" if result["success"] else "danger",
        str(result["message"]),
    )


@router.post("/exchanges/{public_id}/select-market")
def select_market(
    public_id: uuid.UUID,
    db: Session = Depends(get_db),
    market_public_id: uuid.UUID = Form(...),
    active_for_data_collection: str | None = Form(None),
):
    credential = _get_or_404(db, public_id)
    try:
        market = select_market_for_data_collection(
            db,
            credential,
            market_public_id,
            _bool_form(active_for_data_collection),
        )
        message = f"Selected {market.symbol} for market data collection."
        status = "success"
    except Exception as exc:
        message = _form_error(exc)
        status = "danger"
    return _redirect_with_message(f"/exchanges/{public_id}", status, message)


@router.post("/exchanges/{public_id}/capture-market-data")
def capture_exchange_market_data(public_id: uuid.UUID, db: Session = Depends(get_db)):
    credential = _get_or_404(db, public_id)
    result = capture_market_data_for_exchange(db, credential.id)
    return _redirect_with_message(
        f"/exchanges/{public_id}",
        "success" if result["success"] else "danger",
        str(result["message"]),
    )


@router.post("/exchanges/{public_id}/delete")
def delete(public_id: uuid.UUID, db: Session = Depends(get_db)):
    credential = _get_or_404(db, public_id)
    delete_credential(db, credential)
    return RedirectResponse(url="/exchanges", status_code=303)
