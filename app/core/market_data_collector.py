import asyncio
import logging

from app.core.config import get_settings
from app.services.market_data_service import capture_market_data_for_all_active_exchanges


logger = logging.getLogger(__name__)


async def market_data_collection_loop() -> None:
    settings = get_settings()
    interval_seconds = max(settings.market_data_interval_seconds, 1)
    logger.info("Market data auto-collector started with %s second interval.", interval_seconds)

    while True:
        try:
            results = await asyncio.to_thread(capture_market_data_for_all_active_exchanges)
            success_count = sum(1 for result in results if result.get("success"))
            logger.info("Market data auto-collector captured %s of %s active pairs.", success_count, len(results))
        except asyncio.CancelledError:
            logger.info("Market data auto-collector stopped.")
            raise
        except Exception:
            logger.exception("Market data auto-collector iteration failed.")

        await asyncio.sleep(interval_seconds)
