import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import get_settings


logger = logging.getLogger(__name__)


def ensure_database_exists() -> None:
    settings = get_settings()
    url = make_url(settings.database_url)

    if not url.drivername.startswith("postgresql"):
        logger.info("Skipping database creation because DATABASE_URL is not PostgreSQL.")
        return

    db_name = url.database
    if not db_name:
        raise ValueError("DATABASE_URL must include a database name.")

    logger.info("Checking database '%s'.", db_name)
    server_url = url.set(database="postgres")
    engine = create_engine(server_url, isolation_level="AUTOCOMMIT", pool_pre_ping=True)

    try:
        with engine.connect() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :db_name"),
                {"db_name": db_name},
            ).scalar()

            if exists:
                logger.info("Database '%s' already exists.", db_name)
                return

            escaped_db_name = db_name.replace('"', '""')
            connection.execute(text(f'CREATE DATABASE "{escaped_db_name}"'))
            logger.info("Database '%s' created.", db_name)
    finally:
        engine.dispose()


def run_alembic_upgrade_head() -> None:
    settings = get_settings()
    project_root = Path(__file__).resolve().parents[2]
    alembic_ini = project_root / "alembic.ini"

    logger.info("Running Alembic migrations: upgrade head.")
    alembic_config = Config(str(alembic_ini))
    alembic_config.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(alembic_config, "head")
    logger.info("Alembic migrations completed.")


def run_startup_database_tasks() -> None:
    settings = get_settings()

    if settings.auto_create_database:
        ensure_database_exists()
    else:
        logger.info("Automatic database creation is disabled.")

    if settings.auto_migrate_on_startup:
        run_alembic_upgrade_head()
    else:
        logger.info("Automatic Alembic migrations are disabled.")
