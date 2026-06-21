import uuid
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.exchange_credential import ExchangeCredential
from app.models.exchange_market import ExchangeMarket
from app.models.market_data_snapshot import MarketDataSnapshot
from app.services.exchange_service import get_credential, list_credentials
from app.services.market_data_service import (
    capture_market_data_for_all_active_exchanges,
    capture_market_data_for_exchange,
)


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _get_or_404(db: Session, public_id: uuid.UUID) -> ExchangeCredential:
    credential = get_credential(db, public_id)
    if credential is None:
        raise HTTPException(status_code=404, detail="Exchange credential not found")
    return credential


def _dashboard_rows(db: Session) -> list[dict]:
    selected = list(
        db.execute(
            select(ExchangeCredential, ExchangeMarket)
            .join(ExchangeMarket, ExchangeMarket.exchange_credential_id == ExchangeCredential.id)
            .where(
                ExchangeMarket.is_selected_for_data_collection.is_(True),
                ExchangeMarket.is_active.is_(True),
            )
            .order_by(ExchangeCredential.sort_index, ExchangeCredential.title)
        )
    )
    rows = []
    for credential, market in selected:
        latest_snapshot = db.scalar(
            select(MarketDataSnapshot)
            .where(
                MarketDataSnapshot.exchange_credential_id == credential.id,
                MarketDataSnapshot.symbol == market.symbol,
            )
            .order_by(MarketDataSnapshot.captured_at.desc())
            .limit(1)
        )
        rows.append({"credential": credential, "market": market, "snapshot": latest_snapshot})
    return rows


def _redirect_with_message(path: str, status: str, message: str) -> RedirectResponse:
    return RedirectResponse(url=f"{path}?{urlencode({'status': status, 'message': message})}", status_code=303)


@router.get("/market-data")
def market_data_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    status: str | None = Query(None),
    message: str | None = Query(None),
):
    return templates.TemplateResponse(
        "market_data/index.html",
        {
            "request": request,
            "rows": _dashboard_rows(db),
            "has_exchanges": bool(list_credentials(db)),
            "status": status,
            "message": message,
        },
    )


@router.post("/market-data/capture-all")
def capture_all():
    results = capture_market_data_for_all_active_exchanges()
    success_count = sum(1 for result in results if result.get("success"))
    status = "success" if success_count == len(results) and results else "warning"
    message = f"Captured {success_count} of {len(results)} active exchange pairs."
    if not results:
        status = "danger"
        message = "No active exchange pairs are selected for data collection."
    return _redirect_with_message("/market-data", status, message)


@router.post("/market-data/{exchange_public_id}/capture")
def capture_one(exchange_public_id: uuid.UUID, db: Session = Depends(get_db)):
    credential = _get_or_404(db, exchange_public_id)
    result = capture_market_data_for_exchange(db, credential.id)
    return _redirect_with_message(
        "/market-data",
        "success" if result["success"] else "danger",
        str(result["message"]),
    )


@router.get("/market-data/{exchange_public_id}/snapshots")
def snapshots(
    exchange_public_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
):
    credential = _get_or_404(db, exchange_public_id)
    selected_market = db.scalar(
        select(ExchangeMarket).where(
            ExchangeMarket.exchange_credential_id == credential.id,
            ExchangeMarket.is_selected_for_data_collection.is_(True),
        )
    )
    per_page = 50
    snapshot_query = select(MarketDataSnapshot).where(MarketDataSnapshot.exchange_credential_id == credential.id)
    if selected_market is not None:
        snapshot_query = snapshot_query.where(MarketDataSnapshot.symbol == selected_market.symbol)
    latest_snapshots = list(
        db.scalars(
            snapshot_query.order_by(MarketDataSnapshot.captured_at.desc()).offset((page - 1) * per_page).limit(per_page)
        )
    )
    return templates.TemplateResponse(
        "market_data/snapshots.html",
        {
            "request": request,
            "credential": credential,
            "selected_market": selected_market,
            "snapshots": latest_snapshots,
            "page": page,
        },
    )
