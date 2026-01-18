"""
Alembic environment configuration for Plex Kiosk.

This file is executed when running alembic commands and handles:
- Loading all SQLAlchemy models
- Configuring the database connection
- Running migrations in both offline and online modes
"""
from logging.config import fileConfig
from pathlib import Path
import sys

from sqlalchemy import pool, engine_from_config
from sqlalchemy.engine import Connection

from alembic import context

# Add parent directory to path to import app
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import Base and all models
from app.models.database import Base
from app.models.user import User, UserRole, UserStatus
from app.models.request import MediaRequest, RequestStatus, MediaType
from app.models.download import Download, DownloadStatus
from app.models.plex_library import PlexLibraryItem, PlexSyncStatus
from app.models.rename_settings import RenameSettings, TitleMapping
from app.models.system_settings import SystemSettings
from app.models.transfer_history import TransferHistory, TransferStatus

# Import settings for DATABASE_URL
from app.config import get_settings

# Alembic Config object
config = context.config

# Interpret the config file for Python logging (if present)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Get database URL from environment/settings
settings = get_settings()

# Override alembic.ini database URL with environment variable
# Convert asyncpg to psycopg2 for Alembic (sync migrations)
db_url = settings.database_url.replace("+asyncpg", "").replace("postgresql://", "postgresql+psycopg2://")

# Handle SQLite URLs
if "sqlite" in db_url:
    db_url = db_url.replace("sqlite+aiosqlite:///", "sqlite:///")

config.set_main_option("sqlalchemy.url", db_url)

# Add model's MetaData object for 'autogenerate' support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well. By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
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


def do_run_migrations(connection: Connection) -> None:
    """Run migrations with the given connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode with sync engine.

    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        do_run_migrations(connection)

    connectable.dispose()


# Determine which mode to run
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
