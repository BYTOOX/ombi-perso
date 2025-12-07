"""
Database configuration with SQLite.
Async-ready with SQLAlchemy 2.0.
"""
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from ..config import get_settings

settings = get_settings()

# Ensure data directory exists
db_path = settings.database_url.replace("sqlite:///", "")
Path(db_path).parent.mkdir(parents=True, exist_ok=True)

# Sync engine (for migrations and simple operations)
engine = create_engine(
    settings.database_url.replace("sqlite:///", "sqlite+pysqlite:///"),
    connect_args={"check_same_thread": False},
    echo=settings.debug
)

# Async engine
async_engine = create_async_engine(
    settings.database_url.replace("sqlite:///", "sqlite+aiosqlite:///"),
    echo=settings.debug
)

# Session factories
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Alias for pipeline service
async_session_factory = AsyncSessionLocal


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


async def get_db():
    """Dependency for async database sessions."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_sync_db():
    """Get sync database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database tables and create default admin."""
    # Create tables first
    Base.metadata.create_all(bind=engine)
    
    # Import here to avoid circular imports
    from .user import User, UserRole, UserStatus
    from argon2 import PasswordHasher
    
    with SessionLocal() as db:
        # Check if any admin exists
        admin = db.query(User).filter(User.role == UserRole.ADMIN).first()
        if not admin:
            # Hash password using argon2
            ph = PasswordHasher()
            admin_hash = ph.hash("admin")
            
            # Create default admin (ACTIVE status)
            default_admin = User(
                username="admin",
                email="admin@plex-kiosk.local",
                hashed_password=admin_hash,
                role=UserRole.ADMIN,
                status=UserStatus.ACTIVE,
                is_active=True
            )
            db.add(default_admin)
            db.commit()
            print("✓ Default admin user created (admin/admin)")
    
    # Initialize default path settings
    from ..services.settings_service import init_default_settings
    init_default_settings()

