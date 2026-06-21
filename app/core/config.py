import os
from functools import lru_cache

from dotenv import load_dotenv


load_dotenv()


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    app_name: str = os.getenv("APP_NAME", "FuturesML")
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://postgres:postgres@localhost:5432/futuresml",
    )
    fernet_key: str | None = os.getenv("FERNET_KEY")
    auto_migrate_on_startup: bool = _env_bool("AUTO_MIGRATE_ON_STARTUP", False)
    auto_create_database: bool = _env_bool("AUTO_CREATE_DATABASE", False)
    market_data_auto_collect: bool = _env_bool("MARKET_DATA_AUTO_COLLECT", False)
    market_data_interval_seconds: int = int(os.getenv("MARKET_DATA_INTERVAL_SECONDS", "5"))
    order_book_depth: int = int(os.getenv("ORDER_BOOK_DEPTH", "50"))
    label_long_threshold_percent: float = float(os.getenv("LABEL_LONG_THRESHOLD_PERCENT", "0.05"))
    label_short_threshold_percent: float = float(os.getenv("LABEL_SHORT_THRESHOLD_PERCENT", "0.05"))
    micro_candle_timeframe: str = os.getenv("MICRO_CANDLE_TIMEFRAME", "1m")
    micro_candle_limit: int = int(os.getenv("MICRO_CANDLE_LIMIT", "20"))


@lru_cache
def get_settings() -> Settings:
    return Settings()
