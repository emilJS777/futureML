import asyncio
import logging
from datetime import UTC, datetime

from app.core.database import SessionLocal
from app.models.ml_training_session import MlTrainingSession
from app.services.ml_dataset_service import collect_ml_snapshot_for_all_active_pairs, start_training_session, stop_training_session
from app.services.ml_labeling_service import process_pending_labels


logger = logging.getLogger(__name__)
_runner_task: asyncio.Task | None = None
_runner_session_id: int | None = None


async def _training_loop(session_id: int) -> None:
    while True:
        db = SessionLocal()
        try:
            session = db.get(MlTrainingSession, session_id)
            if session is None or session.status != "running":
                logger.info("ML training runner stopped because session is no longer running.")
                return
            interval_seconds = max(session.interval_seconds, 1)
        finally:
            db.close()

        try:
            results = await asyncio.to_thread(collect_ml_snapshot_for_all_active_pairs, session_id)
            label_result = await asyncio.to_thread(process_pending_labels)
            success_count = sum(1 for result in results if result.get("success"))
            logger.info(
                "ML training runner collected %s of %s pairs and labeled %s snapshots.",
                success_count,
                len(results),
                label_result.get("processed", 0),
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("ML training runner iteration failed.")
            db = SessionLocal()
            try:
                session = db.get(MlTrainingSession, session_id)
                if session:
                    session.status = "failed"
                    session.error_message = str(exc)[:1000] or exc.__class__.__name__
                    session.stopped_at = datetime.now(UTC)
                    db.commit()
            finally:
                db.close()
            return

        await asyncio.sleep(interval_seconds)


async def start_ml_training_runner(interval_seconds: int = 5) -> MlTrainingSession:
    global _runner_task, _runner_session_id
    if _runner_task and not _runner_task.done():
        db = SessionLocal()
        try:
            existing = db.get(MlTrainingSession, _runner_session_id)
            if existing:
                return existing
        finally:
            db.close()

    session = await asyncio.to_thread(start_training_session, interval_seconds)
    _runner_session_id = session.id
    _runner_task = asyncio.create_task(_training_loop(session.id))
    return session


async def stop_ml_training_runner() -> MlTrainingSession | None:
    global _runner_task, _runner_session_id
    session_id = _runner_session_id
    if session_id is None:
        db = SessionLocal()
        try:
            latest_running = db.query(MlTrainingSession).filter(MlTrainingSession.status == "running").first()
            session_id = latest_running.id if latest_running else None
        finally:
            db.close()

    if session_id is None:
        return None

    if _runner_task and not _runner_task.done():
        _runner_task.cancel()
        try:
            await _runner_task
        except asyncio.CancelledError:
            pass

    session = await asyncio.to_thread(stop_training_session, session_id)
    _runner_task = None
    _runner_session_id = None
    return session
