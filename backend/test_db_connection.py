#!/usr/bin/env python3
"""
Test PostgreSQL connection and Alembic setup.
Run this after starting docker-compose to verify Phase 0 database migration.
"""
import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from app.models.database import async_engine, is_postgres, settings
from sqlalchemy import text


async def test_connection():
    """Test async PostgreSQL connection."""
    print("=" * 60)
    print("PLEX KIOSK - Database Connection Test")
    print("=" * 60)

    print(f"\nDatabase Type: {'PostgreSQL' if is_postgres else 'SQLite'}")
    print(f"Database URL: {settings.database_url}")
    print(f"Debug Mode: {settings.debug}")

    try:
        print("\n[1/3] Testing async engine connection...")
        async with async_engine.connect() as conn:
            result = await conn.execute(text("SELECT version()"))
            version = result.scalar()
            print(f"✅ Connected to PostgreSQL!")
            print(f"   Version: {version}")

        print("\n[2/3] Checking if tables exist...")
        async with async_engine.connect() as conn:
            result = await conn.execute(text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name;
            """))
            tables = result.fetchall()

            if tables:
                print(f"✅ Found {len(tables)} tables:")
                for table in tables:
                    print(f"   - {table[0]}")
            else:
                print("⚠️  No tables found. Run: alembic upgrade head")

        print("\n[3/3] Checking for admin user...")
        async with async_engine.connect() as conn:
            result = await conn.execute(text("""
                SELECT username, email, role, is_active
                FROM users
                WHERE username = 'admin';
            """))
            admin = result.fetchone()

            if admin:
                print(f"✅ Admin user exists:")
                print(f"   Username: {admin[0]}")
                print(f"   Email: {admin[1]}")
                print(f"   Role: {admin[2]}")
                print(f"   Active: {admin[3]}")
                print(f"\n   Default credentials: admin / admin")
            else:
                print("⚠️  Admin user not found (will be created by migration)")

        print("\n" + "=" * 60)
        print("✅ All tests passed! Database is ready.")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nTroubleshooting:")
        print("1. Make sure PostgreSQL is running: docker-compose up -d postgres")
        print("2. Check connection string in .env")
        print("3. Run migrations: alembic upgrade head")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(test_connection())
