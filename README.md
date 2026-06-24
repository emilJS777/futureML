# FuturesML

First-stage FastAPI project for managing encrypted futures exchange credentials and testing CCXT connectivity.

This stage intentionally does not implement trading, machine learning, order execution, strategy logic, balance fetching, or market data collection.

## Stack

- Python 3.11+
- FastAPI and Jinja2
- SQLAlchemy and Alembic
- PostgreSQL
- CCXT
- python-dotenv
- cryptography/Fernet
- Bootstrap 5

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Update `DATABASE_URL` in `.env` if your PostgreSQL credentials differ.

Generate a Fernet key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Paste the generated value into `.env`:

```env
FERNET_KEY=your-generated-key
```

Run migrations manually when automatic setup is disabled:

```bash
alembic upgrade head
```

Start the app:

```bash
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/exchanges`.

## Automatic Database Setup

In development, set these values in `.env`:

```env
AUTO_CREATE_DATABASE=true
AUTO_MIGRATE_ON_STARTUP=true
```

Then run:

```bash
uvicorn app.main:app --reload
```

The app will create the PostgreSQL database if it is missing and apply Alembic migrations automatically before FastAPI starts serving requests.

PostgreSQL itself must already be running. The app cannot start the PostgreSQL server. The configured database user must also have permission to run `CREATE DATABASE`.

For production, set both flags to `false` unless your deployment intentionally creates databases or runs migrations during application startup.

## Exchange Presets

The app includes these predefined futures exchange options:

| Title | exchange_code | index |
| --- | --- | ---: |
| AscendEX | `ascendex` | 1 |
| Bitfinex | `bitfinex` | 2 |
| MEXC | `mexc` | 3 |
| Binance | `binance` | 4 |
| Gate.io | `gate` | 5 |
| Huobi / HTX | `htx` | 6 |
| WhiteBIT | `whitebit` | 7 |
| Bybit | `bybit` | 8 |
| KuCoin Futures | `kucoinfutures` | 9 |

## Security Notes

API key, API secret, and password/passphrase values are encrypted before storage using Fernet. Details and list pages only show masked API keys. Raw secrets are never rendered back into the UI.

Changing `FERNET_KEY` after credentials are saved will make existing encrypted values undecryptable. Keep the key private and backed up securely.

## CCXT Connection Test

The connection test creates a CCXT exchange instance, enables rate limiting, applies futures/swap defaults where appropriate, calls `load_markets()`, and checks whether futures or swap markets are present.

It does not place orders, fetch balances, or execute any trading logic.

## Market Data Foundation

From an exchange detail page, use `Sync Futures Markets` to discover futures or swap markets from CCXT. After syncing, select one active data pair for that exchange and enable it for data collection.

The `/market-data` dashboard shows all exchanges with an active selected pair. Use `Capture Now` or `Capture All` to store a snapshot with order book top levels, bid/ask spread, mid price, ticker fields, funding data, and open interest when CCXT supports those methods.

Optional background collection is disabled by default:

```env
MARKET_DATA_AUTO_COLLECT=false
MARKET_DATA_INTERVAL_SECONDS=5
ORDER_BOOK_DEPTH=50
```

Set `MARKET_DATA_AUTO_COLLECT=true` in development to run a simple startup background loop that captures all active exchange pairs every configured interval. Unsupported optional CCXT methods are logged and skipped; missing order book support fails that exchange capture.

This foundation still does not implement trading, order creation, positions, ML predictions, or market data strategy logic.

## ML Training Foundation

The `/ml-training` page starts and stops a dataset collection mode. While running, it collects fresh feature snapshots for each active selected futures pair, creates pending labels for 10, 30, and 60 second horizons, and processes labels when enough future data exists.

The dataset now combines order book state, order book dynamics, recent trades/tape pressure, micro candles, funding and open interest, cross-exchange context, latency, and data quality fields. Recent trades are stored in `market_recent_trades_snapshots`, micro OHLCV candles are stored in `market_micro_candles`, and engineered numeric features are stored on `ml_feature_snapshots`.

Label thresholds are controlled by:

```env
LABEL_LONG_THRESHOLD_PERCENT=0.05
LABEL_SHORT_THRESHOLD_PERCENT=0.05
```

Use `Process Labels` to label pending snapshots manually, or let the running training loop process them after each collection cycle. `Train Basic Model` trains an offline `RandomForestClassifier` from stored labeled rows only. At least 1000 labeled rows are required for the selected horizon, and trained model files are saved under `storage/models/`.

Direction labels answer where price ended after a label horizon. Advanced MFE/MAE labels answer how far price moved in favor of, or against, a hypothetical long or short during the horizon. TP/SL hit labels are stored for 0.2%, 0.3%, 0.5%, and 1.0% thresholds so future offline analysis can compare risk/reward, trade quality, and expected value without creating real orders.

These features are only for future ML training and analysis. This ML foundation does not predict live trades and never creates orders, positions, long entries, or short entries.

## ML Experiments

The `/ml-experiments` section trains offline direction-classification experiments from labeled feature snapshots. Experiments use a chronological split: the oldest 70% of eligible rows train the model and the newest 30% remain held out for metrics and shadow backtesting. Rows with a data quality score below 60 are excluded.

Supported models currently include random forest and gradient boosting. Each completed experiment stores accuracy, per-class precision/recall/F1, a confusion matrix, feature importance, and a reproducible model artifact under `storage/models/experiments/`.

Shadow Backtest runs the trained model against its held-out historical rows only. Predictions below the selected confidence threshold and `flat` predictions are skipped. Long predictions use the future labeled return, short predictions use its inverse, and configured fees plus slippage are subtracted from every accepted signal. The dashboard reports win rate, average win/loss, raw and net expectancy, maximum drawdown, and profit factor.

A positive historical backtest does not guarantee real profitability. This module provides offline analysis only: it has no live prediction endpoint, exchange balance access, paper trading, order creation, position management, or execution.
# futureML
