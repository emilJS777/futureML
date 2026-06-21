import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.exchange_credential import ExchangeCredential
from app.models.exchange_market import ExchangeMarket
from app.services.ccxt_service import build_ccxt_exchange


logger = logging.getLogger(__name__)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, (datetime, Decimal)):
        return str(value)
    return value


def list_exchange_markets(db: Session, credential: ExchangeCredential) -> list[ExchangeMarket]:
    return list(
        db.scalars(
            select(ExchangeMarket)
            .where(ExchangeMarket.exchange_credential_id == credential.id)
            .order_by(ExchangeMarket.symbol)
        )
    )


def get_selected_market(db: Session, credential: ExchangeCredential) -> ExchangeMarket | None:
    return db.scalar(
        select(ExchangeMarket).where(
            ExchangeMarket.exchange_credential_id == credential.id,
            ExchangeMarket.is_selected_for_data_collection.is_(True),
        )
    )


def sync_exchange_futures_markets(db: Session, credential: ExchangeCredential) -> dict[str, object]:
    try:
        exchange = build_ccxt_exchange(credential)
        markets = exchange.load_markets()
    except Exception as exc:
        message = f"Could not sync futures markets: {str(exc)[:1000] or exc.__class__.__name__}"
        logger.exception("Futures market sync failed for exchange credential %s.", credential.id)
        return {"success": False, "message": message, "imported": 0, "updated": 0}

    futures_markets = [
        market for market in markets.values() if bool(market.get("swap")) or bool(market.get("future"))
    ]
    if not futures_markets:
        return {
            "success": False,
            "message": "No futures/swap markets were detected for this exchange through CCXT.",
            "imported": 0,
            "updated": 0,
        }

    existing_by_symbol = {
        market.symbol: market
        for market in db.scalars(
            select(ExchangeMarket).where(ExchangeMarket.exchange_credential_id == credential.id)
        )
    }
    imported = 0
    updated = 0

    for raw_market in futures_markets:
        symbol = raw_market.get("symbol")
        if not symbol:
            continue

        market = existing_by_symbol.get(symbol)
        if market is None:
            market = ExchangeMarket(exchange_credential_id=credential.id, symbol=symbol)
            db.add(market)
            imported += 1
        else:
            updated += 1

        market.base = raw_market.get("base")
        market.quote = raw_market.get("quote")
        market.settle = raw_market.get("settle")
        market.market_type = raw_market.get("type")
        market.is_swap = bool(raw_market.get("swap"))
        market.is_future = bool(raw_market.get("future"))
        market.raw_market_json = _json_safe(raw_market)

    db.commit()
    return {
        "success": True,
        "message": f"Synced {len(futures_markets)} futures/swap markets.",
        "imported": imported,
        "updated": updated,
    }


def select_market_for_data_collection(
    db: Session,
    credential: ExchangeCredential,
    market_public_id,
    active_for_data_collection: bool,
) -> ExchangeMarket:
    market = db.scalar(
        select(ExchangeMarket).where(
            ExchangeMarket.public_id == market_public_id,
            ExchangeMarket.exchange_credential_id == credential.id,
        )
    )
    if market is None:
        raise ValueError("Selected market was not found for this exchange.")

    db.execute(
        update(ExchangeMarket)
        .where(ExchangeMarket.exchange_credential_id == credential.id)
        .values(is_selected_for_data_collection=False, is_active=False)
    )
    market.is_selected_for_data_collection = True
    market.is_active = active_for_data_collection
    db.commit()
    db.refresh(market)
    return market
