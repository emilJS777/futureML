import logging
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.exchange_credential import ExchangeCredential
from app.models.exchange_market import ExchangeMarket
from app.models.market_data_snapshot import MarketDataSnapshot
from app.services.ccxt_service import build_ccxt_exchange


logger = logging.getLogger(__name__)


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _datetime_from_ms(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=UTC)
    except (TypeError, ValueError, OSError):
        return None


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


def _has(exchange, capability: str) -> bool:
    return bool(getattr(exchange, "has", {}).get(capability))


def _latest_selected_market(db: Session, credential: ExchangeCredential) -> ExchangeMarket | None:
    return db.scalar(
        select(ExchangeMarket).where(
            ExchangeMarket.exchange_credential_id == credential.id,
            ExchangeMarket.is_selected_for_data_collection.is_(True),
            ExchangeMarket.is_active.is_(True),
        )
    )


def _extract_market_price(raw: dict | None, *keys: str) -> Decimal | None:
    if not raw:
        return None
    for key in keys:
        value = raw.get(key)
        if value is not None:
            return _decimal(value)
    info = raw.get("info") if isinstance(raw.get("info"), dict) else {}
    for key in keys:
        value = info.get(key)
        if value is not None:
            return _decimal(value)
    return None


def capture_market_data_for_exchange(db: Session, exchange_credential_id: int) -> dict[str, object]:
    credential = db.get(ExchangeCredential, exchange_credential_id)
    if credential is None:
        return {"success": False, "message": "Exchange credential not found."}

    market = _latest_selected_market(db, credential)
    if market is None:
        return {"success": False, "message": "No active selected data pair for this exchange."}

    try:
        exchange = build_ccxt_exchange(credential)
    except Exception as exc:
        logger.exception("Could not create CCXT exchange for credential %s.", credential.id)
        return {"success": False, "message": str(exc)[:1000] or exc.__class__.__name__}

    depth = get_settings().order_book_depth
    if not _has(exchange, "fetchOrderBook"):
        return {"success": False, "message": "This exchange does not support fetchOrderBook through CCXT."}

    try:
        order_book = exchange.fetch_order_book(market.symbol, limit=depth)
    except Exception as exc:
        logger.exception("Order book capture failed for %s %s.", credential.exchange_code, market.symbol)
        return {"success": False, "message": f"Order book capture failed: {str(exc)[:1000]}"}

    ticker = None
    funding = None
    open_interest = None

    if _has(exchange, "fetchTicker"):
        try:
            ticker = exchange.fetch_ticker(market.symbol)
        except Exception:
            logger.exception("Ticker capture failed for %s %s.", credential.exchange_code, market.symbol)

    if _has(exchange, "fetchFundingRate"):
        try:
            funding = exchange.fetch_funding_rate(market.symbol)
        except Exception:
            logger.exception("Funding capture failed for %s %s.", credential.exchange_code, market.symbol)

    if _has(exchange, "fetchOpenInterest"):
        try:
            open_interest = exchange.fetch_open_interest(market.symbol)
        except Exception:
            logger.exception("Open interest capture failed for %s %s.", credential.exchange_code, market.symbol)

    bids = (order_book.get("bids") or [])[:depth]
    asks = (order_book.get("asks") or [])[:depth]
    best_bid = _decimal(bids[0][0]) if bids else None
    best_ask = _decimal(asks[0][0]) if asks else None
    spread = best_ask - best_bid if best_bid is not None and best_ask is not None else None
    mid_price = (best_bid + best_ask) / Decimal("2") if best_bid is not None and best_ask is not None else None
    spread_percent = (spread / mid_price * Decimal("100")) if spread is not None and mid_price else None

    snapshot = MarketDataSnapshot(
        exchange_credential_id=credential.id,
        exchange_market_id=market.id,
        exchange_code=credential.exchange_code,
        symbol=market.symbol,
        best_bid=best_bid,
        best_ask=best_ask,
        spread=spread,
        spread_percent=spread_percent,
        mid_price=mid_price,
        last_price=_extract_market_price(ticker, "last", "lastPrice"),
        mark_price=_extract_market_price(ticker, "mark", "markPrice"),
        index_price=_extract_market_price(ticker, "index", "indexPrice"),
        funding_rate=_extract_market_price(funding, "fundingRate"),
        next_funding_time=_datetime_from_ms(funding.get("nextFundingTimestamp")) if funding else None,
        open_interest=_extract_market_price(open_interest, "openInterest", "openInterestAmount"),
        volume_24h=_extract_market_price(ticker, "baseVolume", "volume"),
        quote_volume_24h=_extract_market_price(ticker, "quoteVolume"),
        price_change_percent_24h=_extract_market_price(ticker, "percentage", "priceChangePercent"),
        order_book_bids_json=_json_safe(bids),
        order_book_asks_json=_json_safe(asks),
        order_book_depth=depth,
        raw_ticker_json=_json_safe(ticker),
        raw_funding_json=_json_safe(funding),
        raw_open_interest_json=_json_safe(open_interest),
        captured_at=datetime.now(UTC),
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return {"success": True, "message": "Market data captured.", "snapshot": snapshot}


def capture_market_data_for_all_active_exchanges() -> list[dict[str, object]]:
    db = SessionLocal()
    try:
        credentials = list(
            db.scalars(
                select(ExchangeCredential)
                .join(ExchangeMarket, ExchangeMarket.exchange_credential_id == ExchangeCredential.id)
                .where(
                    ExchangeCredential.is_active.is_(True),
                    ExchangeMarket.is_active.is_(True),
                    ExchangeMarket.is_selected_for_data_collection.is_(True),
                )
                .distinct()
            )
        )
        return [capture_market_data_for_exchange(db, credential.id) for credential in credentials]
    finally:
        db.close()
