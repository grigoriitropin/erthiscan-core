import asyncio
import os
import re
from logging.config import fileConfig

from sqlalchemy.ext.asyncio import create_async_engine

# MODELS IMPORT: Import the models package to ensure all SQLAlchemy models are registered 
# on the metadata BEFORE Alembic starts comparing the code with the database.
import app.models  # noqa: F401
from alembic import context
from app.models.database import Base

# ALEMBIC CONFIG: Access to configuration values from the alembic.ini file.
config = context.config

# LOGGING SETUP: Configures the standard Python logging system as defined in alembic.ini.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# DYNAMIC DB URL: Retrieves the connection string from environment variables.
# This ensures that migrations are applied to the same database used by the application.
db_url = os.getenv("DB_WRITE_URL")
if not db_url:
    raise RuntimeError("DB_WRITE_URL is not set")

# URL NORMALIZATION: Alembic's internal synchronous components do not support the '+asyncpg' prefix.
# We strip this part of the string to provide a standard SQLAlchemy-compatible URL.
sync_url = re.sub(r"\+asyncpg", "", db_url)
config.set_main_option("sqlalchemy.url", sync_url)

# TARGET METADATA: Link Alembic to our application's schema definition.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    OFFLINE MODE: Generates SQL scripts without an active database connection.
    - compare_type=True: Ensures changes in column types are detected.
    - compare_server_default=True: Ensures changes in database-side defaults are detected.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    """
    SYNCHRONOUS WRAPPER: Performs the actual migration operations.
    This function is executed within a synchronous context provided by 'run_sync'.
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations():
    """
    ASYNC RUNNER: Creates an asynchronous engine to handle the database connection.
    - pool_pre_ping=True: Automatically verifies connection health before use.
    """
    engine = create_async_engine(db_url, pool_pre_ping=True)
    async with engine.connect() as conn:
        # ASYNC BRIDGE: migration logic is blocking/synchronous, so we must 
        # use 'run_sync' to execute it safely within the async connection.
        await conn.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    """ONLINE MODE: Entry point for applying migrations to a live database."""
    asyncio.run(run_async_migrations())


# EXECUTION LOGIC: Determines the mode based on Alembic command-line flags.
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
