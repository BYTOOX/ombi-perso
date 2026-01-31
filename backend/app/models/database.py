"""
Database configuration with PostgreSQL (and SQLite fallback).
Async-ready with SQLAlchemy 2.0 + Alembic migrations.

REFACTORED for Phase 0:
- PostgreSQL as default database (via asyncpg)
- Removed init_db() - replaced by Alembic migrations
- Proper connection pooling for production
- SQLite still supported for local dev (if DATABASE_URL set to sqlite)
"""
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from ..config import get_settings

settings = get_settings()

# Detect database type from URL
is_sqlite = settings.database_url.startswith("sqlite")
is_postgres = "postgresql" in settings.database_url

# Create data directory for SQLite if needed
if is_sqlite:
    db_path = settings.database_url.replace("sqlite:///", "").replace("sqlite+aiosqlite:///", "")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

# =============================================================================
# ASYNC ENGINE (Primary - for FastAPI endpoints)
# =============================================================================

if is_sqlite:
    # SQLite async engine (local dev only)
    async_engine = create_async_engine(
        settings.database_url.replace("sqlite:///", "sqlite+aiosqlite:///"),
        echo=settings.debug,
        connect_args={"check_same_thread": False}
    )
else:
    # PostgreSQL async engine (production)
    async_engine = create_async_engine(
        settings.database_url,
        echo=settings.debug,
        pool_pre_ping=True,  # Verify connections before using
        pool_size=10,  # Connection pool size
        max_overflow=20,  # Max connections beyond pool_size
        pool_recycle=3600,  # Recycle connections after 1 hour
    )

# =============================================================================
# SYNC ENGINE (for Alembic migrations only)
# =============================================================================

if is_sqlite:
    # SQLite sync engine
    sync_url = settings.database_url.replace("sqlite:///", "sqlite+pysqlite:///")
    sync_engine = create_engine(
        sync_url,
        echo=settings.debug,
        connect_args={"check_same_thread": False}
    )
else:
    # PostgreSQL sync engine (replace asyncpg with psycopg2 for Alembic)
    sync_url = settings.database_url.replace("+asyncpg", "").replace("postgresql://", "postgresql+psycopg2://")
    sync_engine = create_engine(
        sync_url,
        echo=settings.debug,
        pool_pre_ping=True
    )

# =============================================================================
# SESSION FACTORIES
# =============================================================================

# Async session factory (use this in endpoints)
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False
)

# Sync session factory (legacy code only - prefer async)
SessionLocal = sessionmaker(
    bind=sync_engine,
    autocommit=False,
    autoflush=False
)

# Alias for backward compatibility
async_session_factory = AsyncSessionLocal


# =============================================================================
# BASE MODEL
# =============================================================================

class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


# NOTE: get_db() and get_sync_db() moved to dependencies.py
# Use dependencies.get_async_db() instead


def init_db():
    """
    No-op for backward compatibility.
    Database initialization is now handled by Alembic migrations.
    Run: alembic upgrade head
    """
    pass

