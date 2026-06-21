import logging
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from statistics import median
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.exchange_credential import ExchangeCredential
from app.models.exchange_market import ExchangeMarket
from app.models.market_micro_candle import MarketMicroCandle
from app.models.market_recent_trades_snapshot import MarketRecentTradesSnapshot
from app.models.ml_feature_snapshot import MlFeatureSnapshot
from app.models.ml_snapshot_label import MlSnapshotLabel
from app.models.ml_training_session import MlTrainingSession
from app.services.ccxt_service import build_ccxt_exchange
from app.services.market_data_service import _extract_market_price, _has, _json_safe
from app.core.config import get_settings


logger = logging.getLogger(__name__)
DEFAULT_LABEL_HORIZONS = [10, 30, 60]


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


def _sum_depth(levels: list, count: int) -> Decimal:
    total = Decimal("0")
    for level in levels[:count]:
        if len(level) > 1:
            total += _decimal(level[1]) or Decimal("0")
    return total


def _imbalance(bid_depth: Decimal, ask_depth: Decimal) -> Decimal | None:
    denominator = bid_depth + ask_depth
    if denominator == 0:
        return None
    return (bid_depth - ask_depth) / denominator


def calculate_order_book_features(order_book: dict) -> dict[str, Decimal | None]:
    bids = order_book.get("bids") or []
    asks = order_book.get("asks") or []
    bid_depth_5 = _sum_depth(bids, 5)
    ask_depth_5 = _sum_depth(asks, 5)
    bid_depth_10 = _sum_depth(bids, 10)
    ask_depth_10 = _sum_depth(asks, 10)
    bid_depth_20 = _sum_depth(bids, 20)
    ask_depth_20 = _sum_depth(asks, 20)
    top_bid_size = _decimal(bids[0][1]) if bids and len(bids[0]) > 1 else None
    top_ask_size = _decimal(asks[0][1]) if asks and len(asks[0]) > 1 else None

    return {
        "bid_depth_5": bid_depth_5,
        "ask_depth_5": ask_depth_5,
        "bid_depth_10": bid_depth_10,
        "ask_depth_10": ask_depth_10,
        "bid_depth_20": bid_depth_20,
        "ask_depth_20": ask_depth_20,
        "order_book_imbalance_5": _imbalance(bid_depth_5, ask_depth_5),
        "order_book_imbalance_10": _imbalance(bid_depth_10, ask_depth_10),
        "order_book_imbalance_20": _imbalance(bid_depth_20, ask_depth_20),
        "top_bid_size": top_bid_size,
        "top_ask_size": top_ask_size,
        "bid_wall_score": (top_bid_size / bid_depth_20) if top_bid_size is not None and bid_depth_20 else None,
        "ask_wall_score": (top_ask_size / ask_depth_20) if top_ask_size is not None and ask_depth_20 else None,
    }


def _trade_size(trade: dict) -> Decimal:
    return _decimal(trade.get("amount") or trade.get("size") or trade.get("quantity")) or Decimal("0")


def calculate_trade_features(trades: list[dict]) -> dict[str, object]:
    sizes = [_trade_size(trade) for trade in trades]
    buy_volume = sum((_trade_size(trade) for trade in trades if trade.get("side") == "buy"), Decimal("0"))
    sell_volume = sum((_trade_size(trade) for trade in trades if trade.get("side") == "sell"), Decimal("0"))
    trades_count = len(trades)
    avg_trade_size = (sum(sizes, Decimal("0")) / Decimal(trades_count)) if trades_count else None
    threshold = avg_trade_size * Decimal("3") if avg_trade_size is not None else None
    largest_trade_size = max(sizes) if sizes else None
    large_trade_count = sum(1 for size in sizes if threshold is not None and size >= threshold)
    return {
        "trades_count": trades_count,
        "buy_volume": buy_volume,
        "sell_volume": sell_volume,
        "buy_sell_delta": buy_volume - sell_volume,
        "buy_sell_ratio": (buy_volume / sell_volume) if sell_volume > 0 else None,
        "avg_trade_size": avg_trade_size,
        "large_trade_count": large_trade_count,
        "largest_trade_size": largest_trade_size,
    }


def calculate_candle_features(candles: list[list]) -> dict[str, Decimal | None]:
    if not candles:
        return {
            "candle_return_1": None,
            "candle_return_3": None,
            "candle_volume_1": None,
            "candle_volume_avg_5": None,
            "candle_momentum_5": None,
        }
    closes = [_decimal(candle[4]) for candle in candles if len(candle) > 4]
    volumes = [_decimal(candle[5]) for candle in candles if len(candle) > 5]
    latest_close = closes[-1] if closes else None
    prev_close = closes[-2] if len(closes) >= 2 else None
    close_3 = closes[-4] if len(closes) >= 4 else None
    close_5 = closes[-6] if len(closes) >= 6 else None
    recent_volumes = [volume for volume in volumes[-5:] if volume is not None]
    return {
        "candle_return_1": ((latest_close - prev_close) / prev_close * Decimal("100"))
        if latest_close is not None and prev_close
        else None,
        "candle_return_3": ((latest_close - close_3) / close_3 * Decimal("100"))
        if latest_close is not None and close_3
        else None,
        "candle_volume_1": volumes[-1] if volumes else None,
        "candle_volume_avg_5": (sum(recent_volumes, Decimal("0")) / Decimal(len(recent_volumes)))
        if recent_volumes
        else None,
        "candle_momentum_5": ((latest_close - close_5) / close_5 * Decimal("100"))
        if latest_close is not None and close_5
        else None,
    }


def _delta(current: Decimal | None, previous: Decimal | None) -> Decimal | None:
    if current is None or previous is None:
        return None
    return current - previous


def calculate_dynamic_features(
    current: dict[str, Decimal | None],
    previous: MlFeatureSnapshot | None,
) -> dict[str, Decimal | None]:
    if previous is None:
        return {
            "bid_depth_5_delta": None,
            "ask_depth_5_delta": None,
            "imbalance_5_delta": None,
            "bid_depth_10_delta": None,
            "ask_depth_10_delta": None,
            "imbalance_10_delta": None,
            "spread_delta": None,
            "mid_price_delta": None,
            "wall_shift_score": None,
            "funding_rate_delta": None,
            "funding_rate_abs": abs(current["funding_rate"]) if current.get("funding_rate") is not None else None,
            "funding_pressure_score": current.get("funding_rate"),
        }

    bid_wall_delta = _delta(current.get("bid_wall_score"), previous.bid_wall_score)
    ask_wall_delta = _delta(current.get("ask_wall_score"), previous.ask_wall_score)
    funding_delta = _delta(current.get("funding_rate"), previous.funding_rate)
    funding_abs = abs(current["funding_rate"]) if current.get("funding_rate") is not None else None
    return {
        "bid_depth_5_delta": _delta(current.get("bid_depth_5"), previous.bid_depth_5),
        "ask_depth_5_delta": _delta(current.get("ask_depth_5"), previous.ask_depth_5),
        "imbalance_5_delta": _delta(current.get("order_book_imbalance_5"), previous.order_book_imbalance_5),
        "bid_depth_10_delta": _delta(current.get("bid_depth_10"), previous.bid_depth_10),
        "ask_depth_10_delta": _delta(current.get("ask_depth_10"), previous.ask_depth_10),
        "imbalance_10_delta": _delta(current.get("order_book_imbalance_10"), previous.order_book_imbalance_10),
        "spread_delta": _delta(current.get("spread"), previous.spread),
        "mid_price_delta": _delta(current.get("mid_price"), previous.mid_price),
        "wall_shift_score": (bid_wall_delta - ask_wall_delta)
        if bid_wall_delta is not None and ask_wall_delta is not None
        else None,
        "funding_rate_delta": funding_delta,
        "funding_rate_abs": funding_abs,
        "funding_pressure_score": (funding_abs + abs(funding_delta))
        if funding_abs is not None and funding_delta is not None
        else funding_abs,
    }


def calculate_data_quality(
    *,
    order_book: dict | None,
    ticker: dict | None,
    funding: dict | None,
    open_interest: dict | None,
    trades: list | None,
    candles: list | None,
    latency_ms: int,
) -> tuple[int, int]:
    sources = [order_book, ticker, funding, open_interest, trades, candles]
    missing = sum(1 for source in sources if not source)
    score = 100 - missing * 12
    if latency_ms > 5000:
        score -= 20
    elif latency_ms > 2000:
        score -= 10
    return max(score, 0), missing


def start_training_session(interval_seconds: int = 5) -> MlTrainingSession:
    db = SessionLocal()
    try:
        session = MlTrainingSession(
            title=f"Training session {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')}",
            status="running",
            started_at=datetime.now(UTC),
            interval_seconds=max(interval_seconds, 1),
            label_horizons_json=DEFAULT_LABEL_HORIZONS,
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return session
    finally:
        db.close()


def stop_training_session(session_id: int) -> MlTrainingSession | None:
    db = SessionLocal()
    try:
        session = db.get(MlTrainingSession, session_id)
        if session is None:
            return None
        session.status = "stopped"
        session.stopped_at = datetime.now(UTC)
        db.commit()
        db.refresh(session)
        return session
    finally:
        db.close()


def _active_pairs(db: Session) -> list[tuple[ExchangeCredential, ExchangeMarket]]:
    return list(
        db.execute(
            select(ExchangeCredential, ExchangeMarket)
            .join(ExchangeMarket, ExchangeMarket.exchange_credential_id == ExchangeCredential.id)
            .where(
                ExchangeCredential.is_active.is_(True),
                ExchangeMarket.is_active.is_(True),
                ExchangeMarket.is_selected_for_data_collection.is_(True),
            )
        )
    )


def _cross_exchange_features(db: Session, exchange_code: str, symbol: str, mid_price: Decimal | None) -> dict:
    latest = []
    pairs = _active_pairs(db)
    for credential, market in pairs:
        snapshot = db.scalar(
            select(MlFeatureSnapshot)
            .where(MlFeatureSnapshot.exchange_credential_id == credential.id, MlFeatureSnapshot.symbol == market.symbol)
            .order_by(MlFeatureSnapshot.captured_at.desc())
            .limit(1)
        )
        if snapshot and snapshot.mid_price is not None:
            latest.append(snapshot.mid_price)

    if not latest:
        return {
            "cross_exchange_mid_avg": None,
            "cross_exchange_mid_median": None,
            "cross_exchange_price_deviation_percent": None,
            "cross_exchange_spread_percent": None,
        }

    avg = sum(latest) / Decimal(len(latest))
    med = Decimal(str(median(latest)))
    deviation = ((mid_price - avg) / avg * Decimal("100")) if mid_price is not None and avg else None
    spread = ((max(latest) - min(latest)) / avg * Decimal("100")) if avg else None
    return {
        "cross_exchange_mid_avg": avg,
        "cross_exchange_mid_median": med,
        "cross_exchange_price_deviation_percent": deviation,
        "cross_exchange_spread_percent": spread,
    }


def collect_ml_snapshot_for_exchange(exchange_credential_id: int, session_id: int | None) -> dict[str, object]:
    db = SessionLocal()
    try:
        settings = get_settings()
        capture_started_at = datetime.now(UTC)
        credential = db.get(ExchangeCredential, exchange_credential_id)
        if credential is None:
            return {"success": False, "message": "Exchange credential not found."}
        market = db.scalar(
            select(ExchangeMarket).where(
                ExchangeMarket.exchange_credential_id == credential.id,
                ExchangeMarket.is_selected_for_data_collection.is_(True),
                ExchangeMarket.is_active.is_(True),
            )
        )
        if market is None:
            return {"success": False, "message": "No active selected pair."}

        exchange = build_ccxt_exchange(credential)
        if not _has(exchange, "fetchOrderBook"):
            return {"success": False, "message": "Exchange does not support order book fetch."}

        order_book = exchange.fetch_order_book(market.symbol, limit=50)
        ticker = None
        funding = None
        open_interest = None
        trades = None
        candles = None
        if _has(exchange, "fetchTicker"):
            try:
                ticker = exchange.fetch_ticker(market.symbol)
            except Exception:
                logger.exception("ML ticker fetch failed for %s %s.", credential.exchange_code, market.symbol)
        if _has(exchange, "fetchFundingRate"):
            try:
                funding = exchange.fetch_funding_rate(market.symbol)
            except Exception:
                logger.exception("ML funding fetch failed for %s %s.", credential.exchange_code, market.symbol)
        if _has(exchange, "fetchOpenInterest"):
            try:
                open_interest = exchange.fetch_open_interest(market.symbol)
            except Exception:
                logger.exception("ML open interest fetch failed for %s %s.", credential.exchange_code, market.symbol)
        if _has(exchange, "fetchTrades"):
            try:
                trades = exchange.fetch_trades(market.symbol, limit=100)
            except Exception:
                logger.exception("ML recent trades fetch failed for %s %s.", credential.exchange_code, market.symbol)
        if _has(exchange, "fetchOHLCV"):
            try:
                candles = exchange.fetch_ohlcv(
                    market.symbol,
                    timeframe=settings.micro_candle_timeframe,
                    limit=settings.micro_candle_limit,
                )
            except Exception:
                logger.exception("ML micro candle fetch failed for %s %s.", credential.exchange_code, market.symbol)

        bids = order_book.get("bids") or []
        asks = order_book.get("asks") or []
        best_bid = _decimal(bids[0][0]) if bids else None
        best_ask = _decimal(asks[0][0]) if asks else None
        spread = best_ask - best_bid if best_bid is not None and best_ask is not None else None
        mid_price = (best_bid + best_ask) / Decimal("2") if best_bid is not None and best_ask is not None else None
        spread_percent = (spread / mid_price * Decimal("100")) if spread is not None and mid_price else None
        funding_rate = _extract_market_price(funding, "fundingRate")
        book_features = calculate_order_book_features(order_book)
        trade_features = calculate_trade_features(trades or [])
        candle_features = calculate_candle_features(candles or [])
        cross_features = _cross_exchange_features(db, credential.exchange_code, market.symbol, mid_price)
        previous_snapshot = db.scalar(
            select(MlFeatureSnapshot)
            .where(MlFeatureSnapshot.exchange_credential_id == credential.id, MlFeatureSnapshot.symbol == market.symbol)
            .order_by(MlFeatureSnapshot.captured_at.desc())
            .limit(1)
        )
        current_dynamic_inputs = {
            "spread": spread,
            "mid_price": mid_price,
            "funding_rate": funding_rate,
            **book_features,
        }
        dynamic_features = calculate_dynamic_features(current_dynamic_inputs, previous_snapshot)
        capture_latency_ms = int((datetime.now(UTC) - capture_started_at).total_seconds() * 1000)
        data_quality_score, missing_fields_count = calculate_data_quality(
            order_book=order_book,
            ticker=ticker,
            funding=funding,
            open_interest=open_interest,
            trades=trades,
            candles=candles,
            latency_ms=capture_latency_ms,
        )
        order_book_timestamp = _datetime_from_ms(order_book.get("timestamp"))
        ticker_timestamp = _datetime_from_ms(ticker.get("timestamp")) if ticker else None
        trade_timestamps = [trade.get("timestamp") for trade in (trades or []) if trade.get("timestamp")]
        trades_timestamp = _datetime_from_ms(max(trade_timestamps)) if trade_timestamps else None

        if trades is not None:
            db.add(
                MarketRecentTradesSnapshot(
                    exchange_credential_id=credential.id,
                    exchange_market_id=market.id,
                    exchange_code=credential.exchange_code,
                    symbol=market.symbol,
                    captured_at=datetime.now(UTC),
                    trades_json=_json_safe(trades),
                    **trade_features,
                )
            )

        if candles:
            for candle in candles:
                if len(candle) < 6:
                    continue
                candle_time = _datetime_from_ms(candle[0])
                if candle_time is None:
                    continue
                db.add(
                    MarketMicroCandle(
                        exchange_credential_id=credential.id,
                        exchange_market_id=market.id,
                        exchange_code=credential.exchange_code,
                        symbol=market.symbol,
                        timeframe=settings.micro_candle_timeframe,
                        open=_decimal(candle[1]),
                        high=_decimal(candle[2]),
                        low=_decimal(candle[3]),
                        close=_decimal(candle[4]),
                        volume=_decimal(candle[5]),
                        timestamp=candle_time,
                        raw_ohlcv_json=_json_safe(candle),
                    )
                )

        snapshot = MlFeatureSnapshot(
            training_session_id=session_id,
            exchange_credential_id=credential.id,
            exchange_market_id=market.id,
            exchange_code=credential.exchange_code,
            symbol=market.symbol,
            captured_at=datetime.now(UTC),
            best_bid=best_bid,
            best_ask=best_ask,
            spread=spread,
            spread_percent=spread_percent,
            mid_price=mid_price,
            last_price=_extract_market_price(ticker, "last", "lastPrice"),
            mark_price=_extract_market_price(ticker, "mark", "markPrice"),
            index_price=_extract_market_price(ticker, "index", "indexPrice"),
            funding_rate=funding_rate,
            open_interest=_extract_market_price(open_interest, "openInterest", "openInterestAmount"),
            volume_24h=_extract_market_price(ticker, "baseVolume", "volume"),
            quote_volume_24h=_extract_market_price(ticker, "quoteVolume"),
            price_change_percent_24h=_extract_market_price(ticker, "percentage", "priceChangePercent"),
            capture_latency_ms=capture_latency_ms,
            order_book_timestamp=order_book_timestamp,
            ticker_timestamp=ticker_timestamp,
            trades_timestamp=trades_timestamp,
            data_quality_score=data_quality_score,
            missing_fields_count=missing_fields_count,
            raw_snapshot_json=_json_safe(
                {
                    "order_book": order_book,
                    "ticker": ticker,
                    "funding": funding,
                    "open_interest": open_interest,
                    "trades": trades,
                    "candles": candles,
                }
            ),
            **book_features,
            **trade_features,
            **candle_features,
            **dynamic_features,
            **cross_features,
        )
        db.add(snapshot)
        db.flush()

        session = db.get(MlTrainingSession, session_id) if session_id else None
        horizons = session.label_horizons_json if session else DEFAULT_LABEL_HORIZONS
        for horizon in horizons:
            db.add(MlSnapshotLabel(feature_snapshot_id=snapshot.id, horizon_seconds=int(horizon)))

        db.commit()
        db.refresh(snapshot)
        return {"success": True, "message": "ML feature snapshot collected.", "snapshot_id": snapshot.id}
    except Exception as exc:
        logger.exception("ML snapshot collection failed for exchange credential %s.", exchange_credential_id)
        return {"success": False, "message": str(exc)[:1000] or exc.__class__.__name__}
    finally:
        db.close()


def collect_ml_snapshot_for_all_active_pairs(session_id: int | None) -> list[dict[str, object]]:
    db = SessionLocal()
    try:
        credential_ids = [credential.id for credential, _market in _active_pairs(db)]
    finally:
        db.close()

    results = []
    for credential_id in credential_ids:
        results.append(collect_ml_snapshot_for_exchange(credential_id, session_id))
    return results
