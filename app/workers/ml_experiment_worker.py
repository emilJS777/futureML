import logging
import signal
import time

from app.core.config import get_settings
from app.core.startup import run_startup_database_tasks
from app.services.ml_experiment_service import (
    claim_next_pending_experiment,
    fail_stale_running_experiments,
    run_direction_experiment_training,
)


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger(__name__)
_shutdown_requested = False


def _request_shutdown(_signum, _frame) -> None:
    global _shutdown_requested
    _shutdown_requested = True
    logger.info("ML experiment worker shutdown requested.")


def run_worker_loop() -> None:
    settings = get_settings()
    poll_seconds = max(1, settings.ml_experiment_worker_poll_seconds)
    logger.info("Starting ML experiment worker. poll_seconds=%s", poll_seconds)
    run_startup_database_tasks()
    fail_stale_running_experiments()

    while not _shutdown_requested:
        try:
            fail_stale_running_experiments()
            experiment_id = claim_next_pending_experiment()
            if experiment_id is None:
                time.sleep(poll_seconds)
                continue

            logger.info("ML experiment worker training experiment_id=%s", experiment_id)
            result = run_direction_experiment_training(experiment_id)
            logger.info(
                "ML experiment worker finished experiment_id=%s success=%s message=%s",
                experiment_id,
                result.get("success"),
                result.get("message"),
            )
        except Exception:
            logger.exception("ML experiment worker loop error.")
            time.sleep(poll_seconds)

    logger.info("ML experiment worker stopped.")


def main() -> None:
    signal.signal(signal.SIGTERM, _request_shutdown)
    signal.signal(signal.SIGINT, _request_shutdown)
    run_worker_loop()


if __name__ == "__main__":
    main()
