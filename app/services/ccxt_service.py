from datetime import UTC, datetime

import ccxt
from sqlalchemy.orm import Session

from app.core.security import decrypt_value
from app.models.exchange_credential import ExchangeCredential


FUTURES_OPTIONS_BY_EXCHANGE = {
    "binance": {"defaultType": "future"},
    "bybit": {"defaultType": "swap"},
    "gate": {"defaultType": "swap"},
    "mexc": {"defaultType": "swap"},
    "htx": {"defaultType": "swap"},
    "bitfinex": {"defaultType": "swap"},
    "whitebit": {"defaultType": "swap"},
    "ascendex": {"defaultType": "swap"},
}


def build_ccxt_exchange(credential: ExchangeCredential):
    exchange_class = getattr(ccxt, credential.exchange_code, None)
    if exchange_class is None:
        raise ValueError(f"CCXT does not expose exchange '{credential.exchange_code}'")

    config = {
        "apiKey": decrypt_value(credential.api_key_encrypted),
        "secret": decrypt_value(credential.api_secret_encrypted),
        "enableRateLimit": True,
        "options": FUTURES_OPTIONS_BY_EXCHANGE.get(credential.exchange_code, {}),
    }
    if credential.password_encrypted:
        config["password"] = decrypt_value(credential.password_encrypted)
    return exchange_class(config)


def test_exchange_connection(db: Session, credential: ExchangeCredential) -> dict[str, str]:
    try:
        exchange = build_ccxt_exchange(credential)
        markets = exchange.load_markets()
        futures_markets = [
            symbol
            for symbol, market in markets.items()
            if bool(market.get("swap")) or bool(market.get("future"))
        ]
        if not futures_markets:
            status = "failed"
            message = "Connected to CCXT, but no futures/swap markets were detected."
        else:
            status = "success"
            message = f"Connected successfully. Detected {len(futures_markets)} futures/swap markets."
    except Exception as exc:  # CCXT raises exchange-specific subclasses plus network exceptions.
        status = "failed"
        message = str(exc)[:1000] or exc.__class__.__name__

    credential.last_test_status = status
    credential.last_test_message = message
    credential.last_tested_at = datetime.now(UTC)
    db.commit()
    db.refresh(credential)
    return {"status": status, "message": message}
