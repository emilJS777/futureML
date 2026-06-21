import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.ml_training_session import MlTrainingSession
from app.services.ml_dataset_service import (
    capture_ml_snapshot_debug,
    collect_ml_snapshot_for_all_active_pairs,
    start_training_session,
    stop_training_session,
)
from app.services.ml_labeling_service import process_pending_labels


logger = logging.getLogger(__name__)
_runner_task: asyncio.Task | None = None
_runner_session_id: int | None = None


def _set_session_error(session_id: int, message: str | None) -> None:
    db = SessionLocal()
    try:
        session = db.get(MlTrainingSession, session_id)
        if session:
            session.error_message = message[:1000] if message else None
            db.commit()
    finally:
        db.close()


async def _training_loop(session_id: int) -> None:
    logger.info("ML training runner started for session_id=%s.", session_id)
    iteration = 0
    while True:
        iteration += 1
        db = SessionLocal()
        try:
            session = db.get(MlTrainingSession, session_id)
            if session is None or session.status != "running":
                logger.info(
                    "ML training runner stopped because session is no longer running. session_id=%s iteration=%s",
                    session_id,
                    iteration,
                )
                return
            interval_seconds = max(session.interval_seconds, 1)
        finally:
            db.close()

        try:
            logger.info("ML training runner iteration start. session_id=%s iteration=%s", session_id, iteration)
            results = await asyncio.to_thread(collect_ml_snapshot_for_all_active_pairs, session_id)
            label_result = await asyncio.to_thread(process_pending_labels)
            success_count = sum(1 for result in results if result.get("success"))
            failed_results = [result for result in results if not result.get("success")]
            for result in results:
                if result.get("success"):
                    logger.info(
                        "ML training runner exchange capture success. session_id=%s iteration=%s exchange=%s symbol=%s snapshot_id=%s",
                        session_id,
                        iteration,
                        result.get("exchange_code") or result.get("exchange_credential_id"),
                        result.get("symbol"),
                        result.get("snapshot_id"),
                    )
                else:
                    logger.error(
                        "ML training runner exchange capture failed. session_id=%s iteration=%s credential_id=%s error=%s",
                        session_id,
                        iteration,
                        result.get("exchange_credential_id"),
                        result.get("message"),
                    )
            logger.info(
                "ML training runner iteration completed. session_id=%s iteration=%s success=%s failed=%s labels_processed=%s labels_skipped=%s",
                session_id,
                iteration,
                success_count,
                len(failed_results),
                label_result.get("processed", 0),
                label_result.get("skipped", 0),
            )
            if failed_results:
                _set_session_error(session_id, "; ".join(str(result.get("message")) for result in failed_results))
            else:
                _set_session_error(session_id, None)
        except asyncio.CancelledError:
            logger.info("ML training runner cancelled. session_id=%s iteration=%s", session_id, iteration)
            raise
        except Exception as exc:
            logger.exception("ML training runner iteration failed. session_id=%s iteration=%s", session_id, iteration)
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
    logger.info("ML training background task created for new session_id=%s.", session.id)
    return session


async def restart_running_ml_training_session() -> MlTrainingSession | None:
    global _runner_task, _runner_session_id
    if _runner_task and not _runner_task.done():
        return None

    db = SessionLocal()
    try:
        session = db.scalar(
            select(MlTrainingSession)
            .where(MlTrainingSession.status == "running")
            .order_by(MlTrainingSession.started_at.desc())
            .limit(1)
        )
        if session is None:
            logger.info("No running ML training session found during startup recovery.")
            return None
        session_id = session.id
        session_title = session.title
    finally:
        db.close()

    _runner_session_id = session_id
    _runner_task = asyncio.create_task(_training_loop(session_id))
    logger.info(
        "Recovered running ML training session on app startup. session_id=%s title=%s",
        session_id,
        session_title,
    )
    return session


async def capture_once_debug(session_id: int | None = None) -> dict[str, object]:
    if session_id is None:
        db = SessionLocal()
        try:
            session = db.scalar(
                select(MlTrainingSession)
                .where(MlTrainingSession.status == "running")
                .order_by(MlTrainingSession.started_at.desc())
                .limit(1)
            )
            session_id = session.id if session else None
        finally:
            db.close()
    logger.info("Manual ML capture-once debug started. session_id=%s", session_id)
    result = await asyncio.to_thread(capture_ml_snapshot_debug, session_id)
    logger.info("Manual ML capture-once debug completed. result=%s", result)
    return result


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
